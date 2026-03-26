"""Soft-trash service for documents and Gmail messages.

Role rules:
- staff: can trash (soft-delete) their own uploads; can restore their own items
- admin/owner/super_admin: can trash any item, restore any item,
  permanently delete (purge) individual items, or empty the whole trash
- Auto-purge: items trashed > 30 days are permanently deleted
"""

import os
import logging
from datetime import datetime, timedelta
from app.database import db_conn

log = logging.getLogger(__name__)

TRASH_RETENTION_DAYS = 30


# ─────────── helpers ───────────

def _is_admin_like(user: dict) -> bool:
    return user.get("role") in ("admin", "owner", "super_admin")


def _can_trash_document(user: dict, doc: dict) -> bool:
    """Staff can trash their own uploads; admins can trash anything."""
    if _is_admin_like(user):
        return True
    return doc.get("uploaded_by_user_id") == user["id"]


def _can_trash_gmail(user: dict) -> bool:
    """Only admins can trash gmail messages."""
    return _is_admin_like(user)


# ─────────── DOCUMENTS ───────────

def trash_document(user: dict, doc_id: int) -> bool:
    """Move a document to the soft trash. Returns True on success."""
    with db_conn() as conn:
        doc = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND trashed_at IS NULL",
            (doc_id,)
        ).fetchone()
        if not doc:
            return False
        doc = dict(doc)
        if not _can_trash_document(user, doc):
            return False
        conn.execute(
            "UPDATE documents SET trashed_at = datetime('now'), trashed_by_user_id = ? WHERE id = ?",
            (user["id"], doc_id),
        )
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at)
            VALUES (?, 'document_trashed', ?, datetime('now'))
        """, (user["id"], f"Trashed document #{doc_id}: {doc['original_filename']}"))
    return True


def restore_document(user: dict, doc_id: int) -> bool:
    """Restore a document from the trash. Staff can restore their own."""
    with db_conn() as conn:
        doc = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND trashed_at IS NOT NULL",
            (doc_id,)
        ).fetchone()
        if not doc:
            return False
        doc = dict(doc)
        # Staff can only restore their own
        if not _is_admin_like(user) and doc.get("uploaded_by_user_id") != user["id"]:
            return False
        conn.execute(
            "UPDATE documents SET trashed_at = NULL, trashed_by_user_id = NULL WHERE id = ?",
            (doc_id,),
        )
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at)
            VALUES (?, 'document_restored', ?, datetime('now'))
        """, (user["id"], f"Restored document #{doc_id}: {doc['original_filename']}"))
    return True


def purge_document(user: dict, doc_id: int) -> bool:
    """Permanently delete a trashed document. Admin only."""
    if not _is_admin_like(user):
        return False
    with db_conn() as conn:
        doc = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND trashed_at IS NOT NULL",
            (doc_id,)
        ).fetchone()
        if not doc:
            return False
        doc = dict(doc)
        # Delete physical file
        if doc.get("file_path") and os.path.exists(doc["file_path"]):
            try:
                os.remove(doc["file_path"])
            except OSError as e:
                log.warning("Could not remove file %s: %s", doc["file_path"], e)
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at)
            VALUES (?, 'document_purged', ?, datetime('now'))
        """, (user["id"], f"Purged document #{doc_id}: {doc['original_filename']}"))
    return True


# ─────────── GMAIL MESSAGES ───────────

def trash_gmail_message(user: dict, local_id: int) -> bool:
    """Move a Gmail message to the soft trash. Admin only."""
    if not _is_admin_like(user):
        return False
    with db_conn() as conn:
        msg = conn.execute(
            "SELECT id, subject FROM gmail_messages WHERE id = ? AND trashed_at IS NULL",
            (local_id,)
        ).fetchone()
        if not msg:
            return False
        conn.execute(
            "UPDATE gmail_messages SET trashed_at = datetime('now'), trashed_by_user_id = ? WHERE id = ?",
            (user["id"], local_id),
        )
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at)
            VALUES (?, 'gmail_trashed', ?, datetime('now'))
        """, (user["id"], f"Trashed gmail #{local_id}: {msg['subject'] or '(no subject)'}"))
    return True


def restore_gmail_message(user: dict, local_id: int) -> bool:
    """Restore a Gmail message from the trash. Admin only."""
    if not _is_admin_like(user):
        return False
    with db_conn() as conn:
        msg = conn.execute(
            "SELECT id FROM gmail_messages WHERE id = ? AND trashed_at IS NOT NULL",
            (local_id,)
        ).fetchone()
        if not msg:
            return False
        conn.execute(
            "UPDATE gmail_messages SET trashed_at = NULL, trashed_by_user_id = NULL WHERE id = ?",
            (local_id,),
        )
    return True


def purge_gmail_message(user: dict, local_id: int) -> bool:
    """Permanently delete a trashed Gmail message + its attachments. Admin only."""
    if not _is_admin_like(user):
        return False
    with db_conn() as conn:
        msg = conn.execute(
            "SELECT * FROM gmail_messages WHERE id = ? AND trashed_at IS NOT NULL",
            (local_id,)
        ).fetchone()
        if not msg:
            return False
        msg = dict(msg)
        # Delete attachment files from disk
        atts = conn.execute(
            "SELECT file_path FROM gmail_attachments WHERE gmail_message_id = ?",
            (msg["gmail_message_id"],)
        ).fetchall()
        for att in atts:
            if att["file_path"] and os.path.exists(att["file_path"]):
                try:
                    os.remove(att["file_path"])
                except OSError:
                    pass
        conn.execute("DELETE FROM gmail_attachments WHERE gmail_message_id = ?", (msg["gmail_message_id"],))
        conn.execute("DELETE FROM gmail_messages WHERE id = ?", (local_id,))
    return True


# ─────────── BULK / QUERIES ───────────

def get_trashed_documents(conn, org_id=None) -> list[dict]:
    """Return trashed documents. Scoped to org_id if provided."""
    q = """
        SELECT d.*, u.full_name as uploader_name, tu.full_name as trashed_by_name
        FROM documents d
        LEFT JOIN users u ON u.id = d.uploaded_by_user_id
        LEFT JOIN users tu ON tu.id = d.trashed_by_user_id
        WHERE d.trashed_at IS NOT NULL
    """
    params = []
    if org_id is not None:
        q += " AND d.organization_id = ?"
        params.append(org_id)
    q += " ORDER BY d.trashed_at DESC"
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def get_trashed_gmail_messages(conn, org_id=None) -> list[dict]:
    """Return trashed Gmail messages. Gmail is global (not org-scoped) by design."""
    rows = conn.execute("""
        SELECT gm.*, tu.full_name as trashed_by_name
        FROM gmail_messages gm
        LEFT JOIN users tu ON tu.id = gm.trashed_by_user_id
        WHERE gm.trashed_at IS NOT NULL
        ORDER BY gm.trashed_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def empty_trash(user: dict) -> dict:
    """Permanently delete ALL trashed items. Admin only. Returns counts."""
    if not _is_admin_like(user):
        return {"documents": 0, "gmail": 0}

    counts = {"documents": 0, "gmail": 0}

    with db_conn() as conn:
        # Purge documents
        docs = conn.execute(
            "SELECT id, file_path, original_filename FROM documents WHERE trashed_at IS NOT NULL"
        ).fetchall()
        for doc in docs:
            if doc["file_path"] and os.path.exists(doc["file_path"]):
                try:
                    os.remove(doc["file_path"])
                except OSError:
                    pass
            conn.execute("DELETE FROM documents WHERE id = ?", (doc["id"],))
            counts["documents"] += 1

        # Purge gmail messages
        msgs = conn.execute(
            "SELECT id, gmail_message_id, subject FROM gmail_messages WHERE trashed_at IS NOT NULL"
        ).fetchall()
        for msg in msgs:
            atts = conn.execute(
                "SELECT file_path FROM gmail_attachments WHERE gmail_message_id = ?",
                (msg["gmail_message_id"],)
            ).fetchall()
            for att in atts:
                if att["file_path"] and os.path.exists(att["file_path"]):
                    try:
                        os.remove(att["file_path"])
                    except OSError:
                        pass
            conn.execute("DELETE FROM gmail_attachments WHERE gmail_message_id = ?", (msg["gmail_message_id"],))
            conn.execute("DELETE FROM gmail_messages WHERE id = ?", (msg["id"],))
            counts["gmail"] += 1

        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at)
            VALUES (?, 'trash_emptied', ?, datetime('now'))
        """, (user["id"], f"Emptied trash: {counts['documents']} docs, {counts['gmail']} emails"))

    return counts


def auto_purge_expired() -> dict:
    """Delete items trashed more than TRASH_RETENTION_DAYS ago. Call on app request."""
    cutoff = (datetime.utcnow() - timedelta(days=TRASH_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    counts = {"documents": 0, "gmail": 0}

    with db_conn() as conn:
        # Expired documents
        expired_docs = conn.execute(
            "SELECT id, file_path FROM documents WHERE trashed_at IS NOT NULL AND trashed_at < ?",
            (cutoff,)
        ).fetchall()
        for doc in expired_docs:
            if doc["file_path"] and os.path.exists(doc["file_path"]):
                try:
                    os.remove(doc["file_path"])
                except OSError:
                    pass
            conn.execute("DELETE FROM documents WHERE id = ?", (doc["id"],))
            counts["documents"] += 1

        # Expired gmail messages
        expired_msgs = conn.execute(
            "SELECT id, gmail_message_id FROM gmail_messages WHERE trashed_at IS NOT NULL AND trashed_at < ?",
            (cutoff,)
        ).fetchall()
        for msg in expired_msgs:
            atts = conn.execute(
                "SELECT file_path FROM gmail_attachments WHERE gmail_message_id = ?",
                (msg["gmail_message_id"],)
            ).fetchall()
            for att in atts:
                if att["file_path"] and os.path.exists(att["file_path"]):
                    try:
                        os.remove(att["file_path"])
                    except OSError:
                        pass
            conn.execute("DELETE FROM gmail_attachments WHERE gmail_message_id = ?", (msg["gmail_message_id"],))
            conn.execute("DELETE FROM gmail_messages WHERE id = ?", (msg["id"],))
            counts["gmail"] += 1

    if counts["documents"] or counts["gmail"]:
        log.info("Auto-purge: removed %d docs, %d emails past %d-day retention",
                 counts["documents"], counts["gmail"], TRASH_RETENTION_DAYS)
    return counts
