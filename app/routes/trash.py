"""Trash bin routes — view, restore, purge trashed documents and Gmail messages."""

from flask import Blueprint, render_template, request, redirect, url_for, g, flash, abort
from app.auth_utils import login_required, is_admin_like, org_id_for
from app.database import db_conn
from app.services.trash_service import (
    trash_document, restore_document, purge_document,
    trash_gmail_message, restore_gmail_message, purge_gmail_message,
    get_trashed_documents, get_trashed_gmail_messages,
    empty_trash,
)

bp = Blueprint("trash", __name__, url_prefix="/trash")


@bp.route("")
@login_required
def index():
    """Trash bin overview. Staff see only their own trashed docs."""
    tab = request.args.get("tab", "documents")
    oid = org_id_for(g.user)
    with db_conn() as conn:
        all_docs = get_trashed_documents(conn, org_id=oid)
        all_gmail = get_trashed_gmail_messages(conn)

    # Staff can only see their own trashed documents, no gmail
    if not is_admin_like(g.user):
        all_docs = [d for d in all_docs if d.get("uploaded_by_user_id") == g.user["id"]]
        all_gmail = []

    return render_template("trash/index.html",
        current_user=g.user,
        trashed_docs=all_docs,
        trashed_gmail=all_gmail,
        tab=tab,
    )


# ─── Document trash actions ───

@bp.route("/documents/<int:doc_id>/trash", methods=["POST"])
@login_required
def trash_doc(doc_id):
    """Soft-delete a document."""
    if trash_document(g.user, doc_id):
        flash("Document moved to trash.", "success")
    else:
        flash("Cannot move document to trash.", "error")
    return redirect(request.referrer or url_for("documents.list_docs"))


@bp.route("/documents/<int:doc_id>/restore", methods=["POST"])
@login_required
def restore_doc(doc_id):
    """Restore a document from trash."""
    if restore_document(g.user, doc_id):
        flash("Document restored.", "success")
    else:
        flash("Cannot restore document.", "error")
    return redirect(url_for("trash.index", tab="documents"))


@bp.route("/documents/<int:doc_id>/purge", methods=["POST"])
@login_required
def purge_doc(doc_id):
    """Permanently delete a trashed document. Admin only."""
    if not is_admin_like(g.user):
        abort(403)
    if purge_document(g.user, doc_id):
        flash("Document permanently deleted.", "success")
    else:
        flash("Cannot delete document.", "error")
    return redirect(url_for("trash.index", tab="documents"))


# ─── Gmail trash actions ───

@bp.route("/gmail/<int:local_id>/trash", methods=["POST"])
@login_required
def trash_gmail(local_id):
    """Soft-delete a Gmail message. Admin only."""
    if not is_admin_like(g.user):
        abort(403)
    if trash_gmail_message(g.user, local_id):
        flash("Email moved to trash.", "success")
    else:
        flash("Cannot move email to trash.", "error")
    return redirect(request.referrer or url_for("gmail_inbox.index"))


@bp.route("/gmail/<int:local_id>/restore", methods=["POST"])
@login_required
def restore_gmail(local_id):
    """Restore a Gmail message from trash. Admin only."""
    if not is_admin_like(g.user):
        abort(403)
    if restore_gmail_message(g.user, local_id):
        flash("Email restored.", "success")
    else:
        flash("Cannot restore email.", "error")
    return redirect(url_for("trash.index", tab="gmail"))


@bp.route("/gmail/<int:local_id>/purge", methods=["POST"])
@login_required
def purge_gmail(local_id):
    """Permanently delete a trashed Gmail message. Admin only."""
    if not is_admin_like(g.user):
        abort(403)
    if purge_gmail_message(g.user, local_id):
        flash("Email permanently deleted.", "success")
    else:
        flash("Cannot delete email.", "error")
    return redirect(url_for("trash.index", tab="gmail"))


# ─── Empty all trash ───

@bp.route("/empty", methods=["POST"])
@login_required
def empty_all():
    """Empty all trash. Admin only."""
    if not is_admin_like(g.user):
        abort(403)
    counts = empty_trash(g.user)
    flash(f"Trash emptied: {counts['documents']} documents, {counts['gmail']} emails removed.", "success")
    return redirect(url_for("trash.index"))
