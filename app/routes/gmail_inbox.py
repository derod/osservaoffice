"""CORREOS NUEVOS — Gmail email ingestion page."""
from flask import Blueprint, render_template, request, redirect, url_for, g, abort, flash
from app.auth_utils import login_required, is_admin_like
from app.database import db_conn, get_integration_setting
from app.i18n import translate as _
import logging

log = logging.getLogger(__name__)

bp = Blueprint("gmail_inbox", __name__, url_prefix="/correos-nuevos")


@bp.route("")
@login_required
def index():
    """Main CORREOS NUEVOS page — list imported Gmail messages."""
    tab = request.args.get("tab", "all")
    uid = g.user["id"]

    # Check Gmail configuration status
    try:
        from app.services.gmail_service import gmail_is_configured, gmail_token_exists
        gmail_configured = gmail_is_configured()
        gmail_has_token = gmail_token_exists()
    except Exception:
        gmail_configured = False
        gmail_has_token = False

    gmail_enabled = get_integration_setting("gmail_enabled") == "1"
    last_sync = get_integration_setting("gmail_last_sync") or ""

    with db_conn() as conn:
        # Counts — exclude trashed
        _not_trashed = "AND trashed_at IS NULL"
        count_new = conn.execute(
            f"SELECT COUNT(*) FROM gmail_messages WHERE processed_status = 'new' {_not_trashed}"
        ).fetchone()[0]
        count_matched = conn.execute(
            f"SELECT COUNT(*) FROM gmail_messages WHERE processed_status IN ('matched_existing_client', 'created_new_client', 'attached_to_case') {_not_trashed}"
        ).fetchone()[0]
        count_unmatched = conn.execute(
            f"SELECT COUNT(*) FROM gmail_messages WHERE processed_status = 'new' AND matched_client_id IS NULL {_not_trashed}"
        ).fetchone()[0]
        count_errors = conn.execute(
            f"SELECT COUNT(*) FROM gmail_messages WHERE processed_status = 'error' {_not_trashed}"
        ).fetchone()[0]
        count_ignored = conn.execute(
            f"SELECT COUNT(*) FROM gmail_messages WHERE processed_status = 'ignored' {_not_trashed}"
        ).fetchone()[0]

        # Build query based on tab — always exclude trashed
        where = "gm.trashed_at IS NULL"
        if tab == "new":
            where += " AND gm.processed_status = 'new'"
        elif tab == "matched":
            where += " AND gm.processed_status IN ('matched_existing_client', 'created_new_client', 'attached_to_case')"
        elif tab == "errors":
            where += " AND gm.processed_status = 'error'"
        elif tab == "ignored":
            where += " AND gm.processed_status = 'ignored'"

        messages = conn.execute(f"""
            SELECT gm.*,
                c.full_name AS client_name,
                (SELECT COUNT(*) FROM gmail_attachments ga
                 WHERE ga.gmail_message_id = gm.gmail_message_id AND ga.is_pdf = 1) AS pdf_count
            FROM gmail_messages gm
            LEFT JOIN clients c ON c.id = gm.matched_client_id
            WHERE {where}
            ORDER BY gm.received_at DESC
            LIMIT 100
        """).fetchall()
        messages = [dict(m) for m in messages]

        # All clients for the match dropdown
        clients = conn.execute(
            "SELECT id, full_name, email FROM clients WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()
        clients = [dict(c) for c in clients]

    return render_template("gmail_inbox/index.html",
        current_user=g.user,
        messages=messages,
        clients=clients,
        tab=tab,
        gmail_configured=gmail_configured,
        gmail_has_token=gmail_has_token,
        gmail_enabled=gmail_enabled,
        last_sync=last_sync,
        count_new=count_new,
        count_matched=count_matched,
        count_unmatched=count_unmatched,
        count_errors=count_errors,
        count_ignored=count_ignored,
    )


@bp.route("/<int:local_id>")
@login_required
def detail(local_id):
    """Detail view for a single imported Gmail message."""
    with db_conn() as conn:
        msg = conn.execute("SELECT * FROM gmail_messages WHERE id = ?", (local_id,)).fetchone()
        if not msg:
            abort(404)
        msg = dict(msg)

        # Attachments
        attachments = conn.execute("""
            SELECT ga.*, d.id AS doc_exists
            FROM gmail_attachments ga
            LEFT JOIN documents d ON d.id = ga.document_id
            WHERE ga.gmail_message_id = ?
            ORDER BY ga.created_at
        """, (msg["gmail_message_id"],)).fetchall()
        attachments = [dict(a) for a in attachments]

        # Matched client info
        client = None
        if msg.get("matched_client_id"):
            client = conn.execute(
                "SELECT * FROM clients WHERE id = ?", (msg["matched_client_id"],)
            ).fetchone()
            if client:
                client = dict(client)

        # Matched case info
        case = None
        if msg.get("matched_case_id"):
            case = conn.execute(
                "SELECT * FROM cases WHERE id = ?", (msg["matched_case_id"],)
            ).fetchone()
            if case:
                case = dict(case)

        # All clients and cases for dropdowns
        clients = conn.execute(
            "SELECT id, full_name, email FROM clients WHERE is_active = 1 ORDER BY full_name"
        ).fetchall()
        clients = [dict(c) for c in clients]

        cases_list = conn.execute(
            "SELECT id, title FROM cases WHERE status != 'closed' ORDER BY title"
        ).fetchall()
        cases_list = [dict(c) for c in cases_list]

    return render_template("gmail_inbox/detail.html",
        current_user=g.user,
        msg=msg,
        attachments=attachments,
        client=client,
        case=case,
        clients=clients,
        cases=cases_list,
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    """Manually trigger Gmail sync (admin/owner only)."""
    if not is_admin_like(g.user):
        flash(_("Access denied."), "error")
        return redirect(url_for("gmail_inbox.index"))

    try:
        from app.services.gmail_service import sync_recent_gmail_messages
        counts = sync_recent_gmail_messages(
            max_results=25,
            uploader_user_id=g.user["id"],
        )
        flash(
            _("Sync complete: %(new)s new, %(skipped)s skipped, %(errors)s errors.") % counts
            if hasattr(_, '__call__') else
            f"Sync complete: {counts['new']} new, {counts['skipped']} skipped, {counts['errors']} errors.",
            "success"
        )
    except Exception as e:
        log.error("Gmail sync failed: %s", e)
        flash(f"Gmail sync failed: {e}", "error")

    return redirect(url_for("gmail_inbox.index"))


@bp.route("/<int:local_id>/match-client", methods=["POST"])
@login_required
def match_client(local_id):
    """Assign an existing client to this email."""
    if not is_admin_like(g.user):
        flash(_("Access denied."), "error")
        return redirect(url_for("gmail_inbox.detail", local_id=local_id))

    client_id = request.form.get("client_id", type=int)
    if not client_id:
        flash(_("Please select a client."), "error")
        return redirect(url_for("gmail_inbox.detail", local_id=local_id))

    with db_conn() as conn:
        msg = conn.execute("SELECT * FROM gmail_messages WHERE id = ?", (local_id,)).fetchone()
        if not msg:
            abort(404)

        from app.services.gmail_service import link_message_to_existing_client
        link_message_to_existing_client(conn, local_id, client_id)

    flash(_("Email linked to client."), "success")
    return redirect(url_for("gmail_inbox.detail", local_id=local_id))


@bp.route("/<int:local_id>/create-client", methods=["POST"])
@login_required
def create_client(local_id):
    """Create a new client from this email's sender info."""
    if not is_admin_like(g.user):
        flash(_("Access denied."), "error")
        return redirect(url_for("gmail_inbox.detail", local_id=local_id))

    with db_conn() as conn:
        msg = conn.execute("SELECT * FROM gmail_messages WHERE id = ?", (local_id,)).fetchone()
        if not msg:
            abort(404)
        msg = dict(msg)

        if not msg.get("from_email"):
            flash(_("No sender email found."), "error")
            return redirect(url_for("gmail_inbox.detail", local_id=local_id))

        from app.services.gmail_service import create_client_from_email, link_message_to_existing_client
        client_id = create_client_from_email(conn, msg["from_name"], msg["from_email"])
        conn.execute("""
            UPDATE gmail_messages
            SET matched_client_id = ?, processed_status = 'created_new_client'
            WHERE id = ?
        """, (client_id, local_id))

        # Link documents too
        att_docs = conn.execute(
            "SELECT document_id FROM gmail_attachments WHERE gmail_message_id = ? AND document_id IS NOT NULL",
            (msg["gmail_message_id"],)
        ).fetchall()
        for ad in att_docs:
            conn.execute("UPDATE documents SET client_id = ? WHERE id = ?", (client_id, ad["document_id"]))

    flash(_("New client created and linked."), "success")
    return redirect(url_for("gmail_inbox.detail", local_id=local_id))


@bp.route("/<int:local_id>/ignore", methods=["POST"])
@login_required
def ignore(local_id):
    """Mark email as ignored."""
    with db_conn() as conn:
        row = conn.execute("SELECT id FROM gmail_messages WHERE id = ?", (local_id,)).fetchone()
        if not row:
            abort(404)
        conn.execute("""
            UPDATE gmail_messages SET processed_status = 'ignored' WHERE id = ?
        """, (local_id,))
    flash(_("Email marked as ignored."), "success")
    return redirect(url_for("gmail_inbox.index"))


@bp.route("/<int:local_id>/reprocess", methods=["POST"])
@login_required
def reprocess(local_id):
    """Reset email to 'new' and retry client matching."""
    if not is_admin_like(g.user):
        flash(_("Access denied."), "error")
        return redirect(url_for("gmail_inbox.detail", local_id=local_id))

    with db_conn() as conn:
        msg = conn.execute("SELECT * FROM gmail_messages WHERE id = ?", (local_id,)).fetchone()
        if not msg:
            abort(404)
        msg = dict(msg)

        # Try matching again
        from app.services.gmail_service import match_client_for_email
        client = match_client_for_email(conn, msg.get("from_email"))
        if client:
            conn.execute("""
                UPDATE gmail_messages
                SET matched_client_id = ?, processed_status = 'matched_existing_client',
                    error_message = NULL, last_synced_at = datetime('now')
                WHERE id = ?
            """, (client["id"], local_id))
            flash(_("Client matched successfully."), "success")
        else:
            conn.execute("""
                UPDATE gmail_messages
                SET processed_status = 'new', error_message = NULL,
                    matched_client_id = NULL, last_synced_at = datetime('now')
                WHERE id = ?
            """, (local_id,))
            flash(_("Email reset to new. No matching client found."), "info")

    return redirect(url_for("gmail_inbox.detail", local_id=local_id))


@bp.route("/<int:local_id>/attach-case", methods=["POST"])
@login_required
def attach_case(local_id):
    """Link email and its documents to a case."""
    if not is_admin_like(g.user):
        flash(_("Access denied."), "error")
        return redirect(url_for("gmail_inbox.detail", local_id=local_id))

    case_id = request.form.get("case_id", type=int)
    if not case_id:
        flash(_("Please select a case."), "error")
        return redirect(url_for("gmail_inbox.detail", local_id=local_id))

    with db_conn() as conn:
        msg = conn.execute("SELECT * FROM gmail_messages WHERE id = ?", (local_id,)).fetchone()
        if not msg:
            abort(404)

        conn.execute("""
            UPDATE gmail_messages SET matched_case_id = ?, processed_status = 'attached_to_case'
            WHERE id = ?
        """, (case_id, local_id))

        # Update documents
        att_docs = conn.execute(
            "SELECT document_id FROM gmail_attachments WHERE gmail_message_id = ? AND document_id IS NOT NULL",
            (msg["gmail_message_id"],)
        ).fetchall()
        for ad in att_docs:
            conn.execute("UPDATE documents SET case_id = ? WHERE id = ?", (case_id, ad["document_id"]))

    flash(_("Email attached to case."), "success")
    return redirect(url_for("gmail_inbox.detail", local_id=local_id))
