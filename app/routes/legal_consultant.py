from flask import Blueprint, render_template, g, request, redirect, url_for, flash, abort
from app.auth_utils import login_required, is_admin_like
from app.database import db_conn, get_integration_setting
from app.services.legal_consultant_service import (
    generate_legal_response,
    summarize_title,
    get_jurisdiction_profiles,
    get_jurisdiction_by_name,
    get_confidence_label,
    seed_jurisdiction_profiles,
    save_case_study,
    get_case_studies,
    validate_case_study,
    SUBJECT_AREAS,
    CONSULTATION_TYPES,
)

bp = Blueprint("legal_consultant", __name__, url_prefix="/legal-consultant")


def _load_conversations(user_id: int) -> list[dict]:
    """Return recent conversations for the sidebar (newest first)."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, jurisdiction, subject_area, mentor_mode, confidence_score, "
            "created_at, updated_at "
            "FROM legal_chat_conversations WHERE user_id = ? "
            "ORDER BY updated_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _load_messages(conversation_id: int) -> list[dict]:
    """Return all messages for a conversation, oldest first."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM legal_chat_messages "
            "WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _common_context(active_conversation=None, messages=None):
    """Build the template context dict used by index and conversation views."""
    openai_configured = bool(get_integration_setting("openai_api_key"))
    conversations = _load_conversations(g.user["id"])
    jurisdictions = get_jurisdiction_profiles()

    ctx = dict(
        current_user=g.user,
        openai_configured=openai_configured,
        conversations=conversations,
        active_conversation=active_conversation,
        messages=messages or [],
        jurisdictions=jurisdictions,
        subject_areas=SUBJECT_AREAS,
        consultation_types=CONSULTATION_TYPES,
        get_confidence_label=get_confidence_label,
    )
    if active_conversation and active_conversation.get("jurisdiction"):
        jp = get_jurisdiction_by_name(active_conversation["jurisdiction"])
        ctx["jurisdiction_profile"] = jp
    else:
        ctx["jurisdiction_profile"] = None
    return ctx


@bp.route("")
@login_required
def index():
    """Legal Consultant workspace — no conversation selected."""
    seed_jurisdiction_profiles()  # idempotent
    return render_template("legal_consultant/index.html", **_common_context())


@bp.route("/new", methods=["POST"])
@login_required
def new_conversation():
    """Create a new conversation with optional jurisdiction and settings."""
    jurisdiction = request.form.get("jurisdiction", "").strip() or None
    subject_area = request.form.get("subject_area", "").strip() or None
    consultation_type = request.form.get("consultation_type", "").strip() or None
    mentor_mode = 1 if request.form.get("mentor_mode") else 0

    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO legal_chat_conversations "
            "(user_id, jurisdiction, subject_area, consultation_type, mentor_mode) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], jurisdiction, subject_area, consultation_type, mentor_mode),
        )
        conv_id = cur.lastrowid
    return redirect(url_for("legal_consultant.conversation", conversation_id=conv_id))


@bp.route("/<int:conversation_id>")
@login_required
def conversation(conversation_id: int):
    """Load an existing conversation."""
    with db_conn() as conn:
        conv = conn.execute(
            "SELECT * FROM legal_chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, g.user["id"]),
        ).fetchone()
    if not conv:
        flash("Conversation not found.", "error")
        return redirect(url_for("legal_consultant.index"))

    seed_jurisdiction_profiles()
    messages = _load_messages(conversation_id)
    return render_template(
        "legal_consultant/index.html",
        **_common_context(active_conversation=dict(conv), messages=messages),
    )


@bp.route("/chat", methods=["POST"])
@login_required
def chat():
    """Receive a user message, call OpenAI, persist both messages."""
    conversation_id = request.form.get("conversation_id", type=int)
    user_message = request.form.get("message", "").strip()
    jurisdiction = request.form.get("jurisdiction", "").strip() or None

    if not conversation_id or not user_message:
        flash("Please enter a message.", "error")
        if conversation_id:
            return redirect(url_for("legal_consultant.conversation", conversation_id=conversation_id))
        return redirect(url_for("legal_consultant.index"))

    # Verify ownership
    with db_conn() as conn:
        conv = conn.execute(
            "SELECT * FROM legal_chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, g.user["id"]),
        ).fetchone()
    if not conv:
        flash("Conversation not found.", "error")
        return redirect(url_for("legal_consultant.index"))

    # Update jurisdiction if changed
    if jurisdiction:
        with db_conn() as conn:
            conn.execute(
                "UPDATE legal_chat_conversations SET jurisdiction = ?, updated_at = datetime('now') WHERE id = ?",
                (jurisdiction, conversation_id),
            )

    effective_jurisdiction = jurisdiction or (conv["jurisdiction"] if conv else None)
    subject_area = conv["subject_area"] if conv else None
    mentor_mode = bool(conv["mentor_mode"]) if conv else False

    # Save user message
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO legal_chat_messages (conversation_id, role, content) VALUES (?, 'user', ?)",
            (conversation_id, user_message),
        )
        conn.execute(
            "UPDATE legal_chat_conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )

    # Auto-title from first message
    if not conv["title"]:
        title = summarize_title(user_message)
        with db_conn() as conn:
            conn.execute(
                "UPDATE legal_chat_conversations SET title = ? WHERE id = ?",
                (title, conversation_id),
            )

    # Build message history for OpenAI
    history = _load_messages(conversation_id)
    openai_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Call OpenAI
    try:
        assistant_reply, confidence = generate_legal_response(
            openai_messages, effective_jurisdiction, subject_area, mentor_mode
        )
    except (ValueError, RuntimeError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("legal_consultant.conversation", conversation_id=conversation_id))

    # Save assistant reply and confidence
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO legal_chat_messages (conversation_id, role, content) VALUES (?, 'assistant', ?)",
            (conversation_id, assistant_reply),
        )
        conn.execute(
            "UPDATE legal_chat_conversations SET updated_at = datetime('now'), confidence_score = ? WHERE id = ?",
            (confidence, conversation_id),
        )

    return redirect(url_for("legal_consultant.conversation", conversation_id=conversation_id))


@bp.route("/<int:conversation_id>/settings", methods=["POST"])
@login_required
def update_settings(conversation_id: int):
    """Update conversation settings (mentor mode, subject area, etc.)."""
    with db_conn() as conn:
        conv = conn.execute(
            "SELECT id FROM legal_chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, g.user["id"]),
        ).fetchone()
        if not conv:
            abort(404)
        mentor_mode = 1 if request.form.get("mentor_mode") else 0
        subject_area = request.form.get("subject_area", "").strip() or None
        conn.execute(
            "UPDATE legal_chat_conversations SET mentor_mode = ?, subject_area = ?, updated_at = datetime('now') WHERE id = ?",
            (mentor_mode, subject_area, conversation_id),
        )
    flash("Conversation settings updated.", "success")
    return redirect(url_for("legal_consultant.conversation", conversation_id=conversation_id))


@bp.route("/<int:conversation_id>/delete", methods=["POST"])
@login_required
def delete_conversation(conversation_id: int):
    """Delete a conversation and its messages."""
    with db_conn() as conn:
        conn.execute(
            "DELETE FROM legal_chat_messages WHERE conversation_id IN "
            "(SELECT id FROM legal_chat_conversations WHERE id = ? AND user_id = ?)",
            (conversation_id, g.user["id"]),
        )
        conn.execute(
            "DELETE FROM legal_chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, g.user["id"]),
        )
    return redirect(url_for("legal_consultant.index"))


# ─── Case Studies ───

@bp.route("/<int:conversation_id>/save-study", methods=["POST"])
@login_required
def save_study(conversation_id: int):
    """Save current conversation as a case study."""
    with db_conn() as conn:
        conv = conn.execute(
            "SELECT * FROM legal_chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, g.user["id"]),
        ).fetchone()
    if not conv:
        abort(404)

    title = request.form.get("title", "").strip() or conv["title"] or "Untitled Study"
    summary = request.form.get("summary", "").strip()
    outcome = request.form.get("outcome", "").strip() or None
    lessons = request.form.get("lessons", "").strip() or None

    save_case_study(
        g.user["id"], conversation_id, title,
        conv["jurisdiction"], conv["subject_area"],
        summary, outcome, lessons,
    )
    flash("Conversation saved as case study.", "success")
    return redirect(url_for("legal_consultant.conversation", conversation_id=conversation_id))


@bp.route("/studies")
@login_required
def studies():
    """View case study history."""
    all_studies = get_case_studies()
    return render_template("legal_consultant/studies.html",
        current_user=g.user,
        studies=all_studies,
        get_confidence_label=get_confidence_label,
    )


@bp.route("/studies/<int:study_id>/validate", methods=["POST"])
@login_required
def validate_study(study_id: int):
    """Peer-validate a case study. Requires admin or owner role."""
    if not is_admin_like(g.user):
        abort(403)
    validate_case_study(study_id, g.user["id"])
    flash("Case study validated.", "success")
    return redirect(url_for("legal_consultant.studies"))
