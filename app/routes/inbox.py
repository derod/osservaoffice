from flask import Blueprint, render_template, request, redirect, url_for, g, abort, flash
from app.auth_utils import login_required
from app.database import db_conn
from app.i18n import translate as _
from datetime import datetime, timedelta

bp = Blueprint("inbox", __name__, url_prefix="/inbox")

TRASH_RETENTION_DAYS = 30


def _purge_expired(conn):
    """Auto-purge messages whose soft-delete is older than 30 days."""
    cutoff = (datetime.utcnow() - timedelta(days=TRASH_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    # Null out the user's side when expired; if both sides are null or expired, delete row
    conn.execute("""
        DELETE FROM messages
        WHERE deleted_by_sender_at IS NOT NULL AND deleted_by_sender_at < ?
          AND deleted_by_recipient_at IS NOT NULL AND deleted_by_recipient_at < ?
    """, (cutoff, cutoff))


def _delete_col_for_user(uid, root):
    """Return the column name to soft-delete for this user on this root message."""
    if uid == root["sender_id"]:
        return "deleted_by_sender_at"
    return "deleted_by_recipient_at"


@bp.route("")
@login_required
def index():
    """Show received messages (default), sent, or trash."""
    tab = request.args.get("tab", "received")
    uid = g.user["id"]

    def build_preview(text, limit=120):
        if not text:
            return ""
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}..."

    with db_conn() as conn:
        _purge_expired(conn)

        if tab == "trash":
            # Show root messages this user soft-deleted
            rows = conn.execute("""
                SELECT m.*,
                  CASE WHEN m.sender_id = ? THEN r.full_name ELSE s.full_name END AS other_name,
                  CASE WHEN m.sender_id = ? THEN r.avatar_color ELSE s.avatar_color END AS other_color
                FROM messages m
                JOIN users s ON s.id = m.sender_id
                JOIN users r ON r.id = m.recipient_id
                WHERE m.parent_id IS NULL
                  AND (
                    (m.sender_id = ? AND m.deleted_by_sender_at IS NOT NULL)
                    OR (m.recipient_id = ? AND m.deleted_by_recipient_at IS NOT NULL)
                  )
                ORDER BY m.created_at DESC
            """, (uid, uid, uid, uid)).fetchall()
        elif tab == "sent":
            rows = conn.execute("""
                SELECT m.*, u.full_name AS other_name, u.avatar_color AS other_color
                FROM messages m
                JOIN users u ON u.id = m.recipient_id
                WHERE m.sender_id = ? AND m.parent_id IS NULL
                  AND m.deleted_by_sender_at IS NULL
                ORDER BY m.created_at DESC
            """, (uid,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT m.*,
                  CASE WHEN m.sender_id = ? THEN r.full_name ELSE s.full_name END AS other_name,
                  CASE WHEN m.sender_id = ? THEN r.avatar_color ELSE s.avatar_color END AS other_color
                FROM messages m
                JOIN users s ON s.id = m.sender_id
                JOIN users r ON r.id = m.recipient_id
                WHERE m.parent_id IS NULL
                  AND (m.recipient_id = ? OR m.sender_id = ?)
                  AND (CASE WHEN m.sender_id = ? THEN m.deleted_by_sender_at IS NULL
                            ELSE m.deleted_by_recipient_at IS NULL END)
                GROUP BY m.id
                ORDER BY m.created_at DESC
            """, (uid, uid, uid, uid, uid)).fetchall()

        conversations = []
        for row in rows:
            convo = dict(row)
            latest = conn.execute("""
                SELECT sender_id, body, created_at
                FROM messages
                WHERE id = ? OR parent_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (convo["id"], convo["id"])).fetchone()
            if latest:
                convo["latest_body"] = latest["body"]
                convo["latest_at"] = latest["created_at"]
                convo["latest_sender_label"] = _("You") if latest["sender_id"] == uid else convo["other_name"]
                convo["latest_from_self"] = latest["sender_id"] == uid
            else:
                convo["latest_body"] = convo["body"]
                convo["latest_at"] = convo["created_at"]
                convo["latest_sender_label"] = _("You") if convo["sender_id"] == uid else convo["other_name"]
                convo["latest_from_self"] = convo["sender_id"] == uid

            convo["latest_excerpt"] = build_preview(convo["latest_body"], 140)
            conversations.append(convo)

        # Unread counts per conversation
        unread_counts = {}
        if tab == "received":
            for convo in conversations:
                mid = convo["id"]
                cnt = conn.execute("""
                    SELECT COUNT(*) FROM messages
                    WHERE (id = ? OR parent_id = ?) AND recipient_id = ? AND is_read = 0
                """, (mid, mid, uid)).fetchone()[0]
                unread_counts[mid] = cnt

        # Trash count for badge
        trash_count = conn.execute("""
            SELECT COUNT(*) FROM messages
            WHERE parent_id IS NULL
              AND (
                (sender_id = ? AND deleted_by_sender_at IS NOT NULL)
                OR (recipient_id = ? AND deleted_by_recipient_at IS NOT NULL)
              )
        """, (uid, uid)).fetchone()[0]

        # All users for compose dropdown
        users = conn.execute(
            "SELECT id, full_name, avatar_color FROM users WHERE id != ? AND is_active = 1 ORDER BY full_name",
            (uid,)
        ).fetchall()

    return render_template("inbox/index.html",
        current_user=g.user,
        conversations=conversations,
        unread_counts=unread_counts,
        trash_count=trash_count,
        tab=tab,
        users=[dict(u) for u in users],
    )


@bp.route("/thread/<int:msg_id>")
@login_required
def thread(msg_id):
    """View a conversation thread."""
    uid = g.user["id"]

    with db_conn() as conn:
        root = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if not root:
            abort(404)
        if uid not in (root["sender_id"], root["recipient_id"]):
            abort(403)

        replies = conn.execute("""
            SELECT m.*, u.full_name AS sender_name, u.avatar_color AS sender_color
            FROM messages m
            JOIN users u ON u.id = m.sender_id
            WHERE m.parent_id = ?
            ORDER BY m.created_at ASC
        """, (msg_id,)).fetchall()

        # Mark unread messages in this thread as read
        conn.execute("""
            UPDATE messages SET is_read = 1
            WHERE (id = ? OR parent_id = ?) AND recipient_id = ? AND is_read = 0
        """, (msg_id, msg_id, uid))

        sender = conn.execute("SELECT full_name, avatar_color FROM users WHERE id = ?",
                              (root["sender_id"],)).fetchone()
        recipient = conn.execute("SELECT full_name, avatar_color FROM users WHERE id = ?",
                                 (root["recipient_id"],)).fetchone()

        # Check if this thread is in the user's trash
        col = _delete_col_for_user(uid, root)
        is_trashed = root[col] is not None

    return render_template("inbox/thread.html",
        current_user=g.user,
        root=dict(root),
        replies=[dict(r) for r in replies],
        sender=dict(sender),
        recipient=dict(recipient),
        is_trashed=is_trashed,
    )


@bp.route("/compose", methods=["POST"])
@login_required
def compose():
    """Send a new message (starts a conversation)."""
    recipient_id = request.form.get("recipient_id", type=int)
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()

    if not recipient_id or not subject or not body:
        flash(_("All fields are required."), "error")
        return redirect(url_for("inbox.index"))

    if recipient_id == g.user["id"]:
        flash(_("You cannot message yourself."), "error")
        return redirect(url_for("inbox.index"))

    with db_conn() as conn:
        conn.execute("""
            INSERT INTO messages (sender_id, recipient_id, subject, body)
            VALUES (?, ?, ?, ?)
        """, (g.user["id"], recipient_id, subject, body))

    flash(_("Message sent."), "success")
    return redirect(url_for("inbox.index", tab="sent"))


@bp.route("/reply/<int:msg_id>", methods=["POST"])
@login_required
def reply(msg_id):
    """Reply to an existing conversation thread."""
    body = request.form.get("body", "").strip()
    if not body:
        flash(_("Reply cannot be empty."), "error")
        return redirect(url_for("inbox.thread", msg_id=msg_id))

    uid = g.user["id"]

    with db_conn() as conn:
        root = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if not root:
            abort(404)
        if uid not in (root["sender_id"], root["recipient_id"]):
            abort(403)

        recipient_id = root["recipient_id"] if uid == root["sender_id"] else root["sender_id"]

        conn.execute("""
            INSERT INTO messages (sender_id, recipient_id, parent_id, subject, body)
            VALUES (?, ?, ?, ?, ?)
        """, (uid, recipient_id, msg_id, root["subject"], body))

    return redirect(url_for("inbox.thread", msg_id=msg_id))


@bp.route("/delete/<int:msg_id>", methods=["POST"])
@login_required
def delete(msg_id):
    """Soft-delete a conversation for the current user (move to trash)."""
    uid = g.user["id"]
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    with db_conn() as conn:
        root = conn.execute("SELECT * FROM messages WHERE id = ? AND parent_id IS NULL", (msg_id,)).fetchone()
        if not root:
            abort(404)
        if uid not in (root["sender_id"], root["recipient_id"]):
            abort(403)

        col = _delete_col_for_user(uid, root)
        conn.execute(f"UPDATE messages SET {col} = ? WHERE id = ? OR parent_id = ?", (now, msg_id, msg_id))

    flash(_("Conversation moved to trash."), "success")
    return redirect(url_for("inbox.index"))


@bp.route("/restore/<int:msg_id>", methods=["POST"])
@login_required
def restore(msg_id):
    """Restore a conversation from trash."""
    uid = g.user["id"]

    with db_conn() as conn:
        root = conn.execute("SELECT * FROM messages WHERE id = ? AND parent_id IS NULL", (msg_id,)).fetchone()
        if not root:
            abort(404)
        if uid not in (root["sender_id"], root["recipient_id"]):
            abort(403)

        col = _delete_col_for_user(uid, root)
        conn.execute(f"UPDATE messages SET {col} = NULL WHERE id = ? OR parent_id = ?", (msg_id, msg_id))

    flash(_("Conversation restored."), "success")
    return redirect(url_for("inbox.index", tab="trash"))
