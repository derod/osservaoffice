from flask import Blueprint, render_template, request, redirect, url_for, g, send_file, abort, jsonify, Response, flash
from app.auth_utils import login_required, is_admin_like, org_filter, org_id_for
from app.database import db_conn, get_integration_setting, set_integration_setting
from datetime import datetime, timedelta
import os, uuid

# ───────── AVAILABILITY ─────────
avail_bp = Blueprint("availability", __name__, url_prefix="/availability")
WORK_START = 8
WORK_END = 18

def get_free_slots(user_id, date, conn):
    day_start = date.replace(hour=WORK_START, minute=0, second=0)
    day_end = date.replace(hour=WORK_END, minute=0, second=0)
    appts = conn.execute("""
        SELECT title, start_datetime, end_datetime FROM appointments
        WHERE assigned_to_user_id=? AND start_datetime>=? AND start_datetime<=?
        ORDER BY start_datetime
    """, (user_id,
          date.replace(hour=0,minute=0,second=0).strftime("%Y-%m-%d %H:%M:%S"),
          date.replace(hour=23,minute=59,second=59).strftime("%Y-%m-%d %H:%M:%S")
    )).fetchall()

    busy = []
    for a in appts:
        s = datetime.strptime(a["start_datetime"][:19], "%Y-%m-%d %H:%M:%S")
        e = datetime.strptime(a["end_datetime"][:19], "%Y-%m-%d %H:%M:%S")
        s = max(s, day_start); e = min(e, day_end)
        if s < e:
            busy.append({"start": s, "end": e, "title": a["title"]})
    return busy

def to_pct(dt):
    total = (WORK_END - WORK_START) * 60
    mins = (dt.hour - WORK_START) * 60 + dt.minute
    return max(0, min(100, (mins / total) * 100))

def to_width_pct(start, end):
    total = (WORK_END - WORK_START) * 60
    mins = (end - start).seconds // 60
    return max(0, min(100, (mins / total) * 100))

@avail_bp.route("")
@login_required
def index():
    employee_id = request.args.get("employee_id", type=int)
    range_type = request.args.get("range_type", "today")
    today = datetime.utcnow().replace(hour=0, minute=0, second=0)

    uc, up = org_filter(g.user)
    with db_conn() as conn:
        hide_roles = "('owner')" if g.user["role"] == "super_admin" else "('owner','super_admin')"
        all_users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1 AND role NOT IN {hide_roles}{uc} ORDER BY full_name", up
        ).fetchall()]

        if employee_id:
            selected_users = [u for u in all_users if u["id"] == employee_id]
        else:
            selected_users = all_users

        availability_data = []
        if range_type == "today":
            for u in selected_users:
                busy = get_free_slots(u["id"], today, conn)
                availability_data.append({"user": u, "busy_blocks": busy})

    hours_labels = list(range(WORK_START, WORK_END + 1))
    return render_template("availability/index.html",
        current_user=g.user,
        all_users=all_users,
        selected_employee_id=employee_id,
        range_type=range_type,
        availability_data=availability_data,
        hours_labels=hours_labels,
        to_pct=to_pct, to_width_pct=to_width_pct,
        today=today, now=datetime.utcnow(),
    )


# ───────── SCHEDULE REQUESTS ─────────
sr_bp = Blueprint("schedule_requests", __name__, url_prefix="/schedule-requests")

@sr_bp.route("")
@login_required
def list_requests():
    status_filter = request.args.get("status_filter", "all")
    oc, op = org_filter(g.user, alias="sr")
    uc, up = org_filter(g.user)
    with db_conn() as conn:
        q = f"""
            SELECT sr.*,
                emp.full_name as emp_name, emp.avatar_color as emp_color,
                cr.full_name as creator_name,
                ap.full_name as approver_name
            FROM schedule_requests sr
            LEFT JOIN users emp ON emp.id=sr.requested_employee_id
            LEFT JOIN users cr ON cr.id=sr.created_by_user_id
            LEFT JOIN users ap ON ap.id=sr.approved_by_user_id
            WHERE 1=1{oc}
        """
        params = list(op)
        if g.user["role"] == "staff":
            q += " AND sr.requested_employee_id=?"; params.append(g.user["id"])
            if status_filter != "all":
                q += " AND sr.status=?"; params.append(status_filter)
        else:
            if status_filter != "all":
                q += " AND sr.status=?"; params.append(status_filter)
        q += " ORDER BY sr.created_at DESC"
        reqs = [dict(r) for r in conn.execute(q, params).fetchall()]
        all_users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()]

    return render_template("schedule_requests/list.html",
        current_user=g.user, schedule_requests=reqs,
        all_users=all_users, status_filter=status_filter,
    )

@sr_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_request():
    uc2, up2 = org_filter(g.user)
    if request.method == "POST":
        f = request.form
        emp_id = g.user["id"] if g.user["role"] == "staff" else (f.get("requested_employee_id") or g.user["id"])
        start_dt = f.get("start_date","") + " " + f.get("start_time","09:00") + ":00"
        end_dt = f.get("end_date","") + " " + f.get("end_time","10:00") + ":00"
        oid = org_id_for(g.user)
        with db_conn() as conn:
            conn.execute("""
                INSERT INTO schedule_requests
                    (requested_employee_id, created_by_user_id, request_type,
                     requested_start_datetime, requested_end_datetime,
                     reason, notes, priority, status, organization_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (emp_id, g.user["id"], f.get("request_type","new_meeting"),
                  start_dt, end_dt,
                  f.get("reason",""), f.get("notes",""),
                  f.get("priority","medium"), "pending", oid))
        return redirect(url_for("schedule_requests.list_requests"))

    employee_id = request.args.get("employee_id", type=int)
    with db_conn() as conn:
        all_users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc2} ORDER BY full_name", up2
        ).fetchall()]
    return render_template("schedule_requests/form.html",
        current_user=g.user, all_users=all_users,
        selected_employee_id=employee_id or (g.user["id"] if g.user["role"] == "staff" else None),
    )

@sr_bp.route("/<int:req_id>/approve", methods=["POST"])
@login_required
def approve(req_id):
    if not is_admin_like(g.user):
        return redirect(url_for("schedule_requests.list_requests"))
    oc, op = org_filter(g.user)
    with db_conn() as conn:
        sr = conn.execute(
            f"SELECT * FROM schedule_requests WHERE id=?{oc}", [req_id] + op
        ).fetchone()
        if sr:
            sr = dict(sr)
            emp = conn.execute("SELECT full_name FROM users WHERE id=?", (sr["requested_employee_id"],)).fetchone()
            title = f"{sr['request_type'].replace('_',' ').title()} - {emp['full_name'] if emp else 'Employee'}"
            oid = sr.get("organization_id") or org_id_for(g.user)
            cur = conn.execute("""
                INSERT INTO appointments (title, description, start_datetime, end_datetime,
                    assigned_to_user_id, appointment_type, created_by_user_id, organization_id)
                VALUES (?,?,?,?,?,?,?,?)
            """, (title, sr.get("reason",""), sr["requested_start_datetime"],
                  sr["requested_end_datetime"], sr["requested_employee_id"],
                  "meeting", g.user["id"], oid))
            appt_id = cur.lastrowid
            conn.execute("""
                UPDATE schedule_requests SET status='approved',
                    approved_by_user_id=?, resolved_at=datetime('now'),
                    created_appointment_id=? WHERE id=?
            """, (g.user["id"], appt_id, req_id))
    return redirect(url_for("schedule_requests.list_requests"))

@sr_bp.route("/<int:req_id>/deny", methods=["POST"])
@login_required
def deny(req_id):
    if not is_admin_like(g.user):
        return redirect(url_for("schedule_requests.list_requests"))
    reason = request.form.get("denial_reason", "")
    with db_conn() as conn:
        conn.execute("""
            UPDATE schedule_requests SET status='denied',
                denial_reason=?, approved_by_user_id=?, resolved_at=datetime('now')
            WHERE id=?
        """, (reason, g.user["id"], req_id))
    return redirect(url_for("schedule_requests.list_requests"))


# ───────── DOCUMENTS ─────────
docs_bp = Blueprint("documents", __name__, url_prefix="/documents")
UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app", "static", "uploads"),
)
MAX_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "20")) * 1024 * 1024
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".txt", ".xls", ".xlsx"}

@docs_bp.route("")
@login_required
def list_docs():
    case_id = request.args.get("case_id", type=int)
    client_id = request.args.get("client_id", type=int)
    dc, dp = org_filter(g.user, alias="d")
    uc3, up3 = org_filter(g.user)
    with db_conn() as conn:
        q = f"""
            SELECT d.*, u.full_name as uploader_name,
                c.title as case_title, cl.full_name as client_name
            FROM documents d
            LEFT JOIN users u ON u.id=d.uploaded_by_user_id
            LEFT JOIN cases c ON c.id=d.case_id
            LEFT JOIN clients cl ON cl.id=d.client_id
            WHERE d.trashed_at IS NULL{dc}
        """
        params = list(dp)
        if case_id:
            q += " AND d.case_id=?"; params.append(case_id)
        if client_id:
            q += " AND d.client_id=?"; params.append(client_id)
        q += " ORDER BY d.created_at DESC"
        docs = [dict(r) for r in conn.execute(q, params).fetchall()]
        all_cases = [dict(r) for r in conn.execute(
            f"SELECT id, title FROM cases WHERE 1=1{uc3} ORDER BY title", up3
        ).fetchall()]
        all_clients = [dict(r) for r in conn.execute(
            f"SELECT id, full_name FROM clients WHERE 1=1{uc3} ORDER BY full_name", up3
        ).fetchall()]
    return render_template("documents/list.html",
        current_user=g.user, documents=docs,
        all_cases=all_cases, all_clients=all_clients,
        filter_case_id=case_id, filter_client_id=client_id,
    )

@docs_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return redirect(url_for("documents.list_docs"))

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return redirect(url_for("documents.list_docs"))

    contents = file.read()
    if len(contents) > MAX_SIZE:
        return redirect(url_for("documents.list_docs"))

    stored_name = uuid.uuid4().hex + ext
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, stored_name)
    with open(file_path, "wb") as f_out:
        f_out.write(contents)

    case_id = request.form.get("case_id") or None
    client_id = request.form.get("client_id") or None
    oid = org_id_for(g.user)

    with db_conn() as conn:
        conn.execute("""
            INSERT INTO documents (original_filename, stored_filename, file_path,
                mime_type, file_size, case_id, client_id, uploaded_by_user_id, description, organization_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (file.filename, stored_name, file_path,
              file.mimetype, len(contents),
              case_id, client_id,
              g.user["id"], request.form.get("description",""), oid))

    if case_id:
        return redirect(url_for("cases.detail", case_id=case_id))
    return redirect(url_for("documents.list_docs"))

@docs_bp.route("/<int:doc_id>/download")
@login_required
def download(doc_id):
    oc, op = org_filter(g.user)
    with db_conn() as conn:
        doc = conn.execute(
            f"SELECT * FROM documents WHERE id=?{oc}", [doc_id] + op
        ).fetchone()
    if not doc or not os.path.exists(doc["file_path"]):
        abort(404)
    return send_file(doc["file_path"], as_attachment=True, download_name=doc["original_filename"])

@docs_bp.route("/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_doc(doc_id):
    """Soft-delete: move document to trash instead of permanent deletion."""
    from app.services.trash_service import trash_document
    if trash_document(g.user, doc_id):
        flash("Document moved to trash.", "success")
    else:
        flash("Cannot delete document.", "error")
    return redirect(request.referrer or url_for("documents.list_docs"))


@docs_bp.route("/<int:doc_id>/view")
@login_required
def view_doc(doc_id):
    """Stream a PDF inline so it can be embedded in an iframe."""
    oc, op = org_filter(g.user)
    with db_conn() as conn:
        doc = conn.execute(
            f"SELECT * FROM documents WHERE id=?{oc}", [doc_id] + op
        ).fetchone()
    if not doc:
        abort(404)
    doc = dict(doc)

    # Role check: staff may only view docs linked to their assigned cases
    if g.user["role"] == "staff" and doc.get("case_id"):
        with db_conn() as conn:
            assigned = conn.execute(
                "SELECT 1 FROM case_assignments WHERE case_id=? AND user_id=?",
                (doc["case_id"], g.user["id"])
            ).fetchone()
        if not assigned:
            abort(403)

    path = doc["file_path"]
    if not os.path.exists(path):
        abort(404)

    ext = os.path.splitext(path)[1].lower()
    if ext != ".pdf":
        abort(400)

    with open(path, "rb") as f:
        data = f.read()

    return Response(
        data,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc["original_filename"]}"'}
    )


@docs_bp.route("/<int:doc_id>/summary", methods=["POST"])
@login_required
def summarize_doc(doc_id):
    """Read a PDF server-side, call OpenAI, return JSON summary."""
    import requests as http_requests

    with db_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        return jsonify({"error": "Document not found."}), 404
    doc = dict(doc)

    # Role check: staff may only summarise docs linked to their assigned cases
    if g.user["role"] == "staff" and doc.get("case_id"):
        with db_conn() as conn:
            assigned = conn.execute(
                "SELECT 1 FROM case_assignments WHERE case_id=? AND user_id=?",
                (doc["case_id"], g.user["id"])
            ).fetchone()
        if not assigned:
            return jsonify({"error": "Access denied."}), 403

    ext = os.path.splitext(doc["file_path"])[1].lower()
    if ext != ".pdf":
        return jsonify({"error": "Only PDF documents can be summarised."}), 400

    # Extract text
    try:
        from app.utils.pdf_utils import prepare_text_for_summary
        text, truncated = prepare_text_for_summary(doc["file_path"])
    except FileNotFoundError:
        return jsonify({"error": "PDF file not found on disk."}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    if not text.strip():
        return jsonify({"error": "No text could be extracted from this PDF."}), 422

    # Get API key: DB first, env fallback
    api_key = get_integration_setting("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify({
            "error": "No OpenAI API key configured. An admin must add it in Settings → AI Integrations."
        }), 400

    truncation_note = " [Note: document was truncated to fit context limits.]" if truncated else ""

    system_prompt = (
        "You are a legal document analyst. Analyse the provided document and respond "
        "with a JSON object containing exactly three keys: "
        "\"summary\" (a 2-3 sentence plain-language summary), "
        "\"key_points\" (a list of up to 5 concise bullet strings), and "
        "\"next_steps\" (a list of up to 3 suggested action items for the legal team). "
        "Respond ONLY with valid JSON, no markdown fences."
    )
    user_prompt = f"Document filename: {doc['original_filename']}{truncation_note}\n\n{text}"

    try:
        resp = http_requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 600,
            },
            timeout=30,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to reach OpenAI: {str(e)}"}), 502

    if resp.status_code == 401:
        return jsonify({"error": "Invalid OpenAI API key. Check Settings → AI Integrations."}), 400
    if resp.status_code == 429:
        return jsonify({"error": "OpenAI rate limit reached. Please try again shortly."}), 429
    if not resp.ok:
        return jsonify({"error": f"OpenAI API error {resp.status_code}: {resp.text[:200]}"}), 502

    content = ""
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        import json as _json
        result = _json.loads(content)
        # Normalise expected keys
        return jsonify({
            "summary": result.get("summary", ""),
            "key_points": result.get("key_points", []),
            "next_steps": result.get("next_steps", []),
        })
    except Exception:
        return jsonify({"error": "Could not parse OpenAI response.", "raw": content[:500]}), 502


# ───────── CLIENTS ─────────
clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


def _client_in_user_org(conn, client_id, user):
    """Return client row dict if it exists AND belongs to user's org (or user is super_admin), else None."""
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not row:
        return None
    if user.get("role") == "super_admin":
        return dict(row)
    if row["organization_id"] != user.get("organization_id"):
        return None
    return dict(row)


@clients_bp.route("")
@login_required
def list_clients():
    uc, up = org_filter(g.user)
    with db_conn() as conn:
        clients = conn.execute(
            f"SELECT * FROM clients WHERE 1=1{uc} ORDER BY full_name", up
        ).fetchall()
        client_data = []
        for c in clients:
            c = dict(c)
            active = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE client_id=? AND status!='closed'", (c["id"],)
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE client_id=?", (c["id"],)
            ).fetchone()[0]
            client_data.append({"client": c, "active_cases": active, "total_cases": total})
    return render_template("clients/list.html",
        current_user=g.user, client_data=client_data,
    )

@clients_bp.route("/new", methods=["GET","POST"])
@login_required
def new_client():
    if not is_admin_like(g.user):
        return redirect(url_for("clients.list_clients"))
    if request.method == "POST":
        f = request.form
        oid = org_id_for(g.user)
        with db_conn() as conn:
            cur = conn.execute("""
                INSERT INTO clients (full_name, company_name, email, phone, address, notes, organization_id)
                VALUES (?,?,?,?,?,?,?)
            """, (f["full_name"], f.get("company_name") or None,
                  f.get("email") or None, f.get("phone") or None,
                  f.get("address") or None, f.get("notes") or None, oid))
            new_id = cur.lastrowid
        return redirect(url_for("clients.detail", client_id=new_id))
    return render_template("clients/form.html", current_user=g.user, client=None)

@clients_bp.route("/<int:client_id>")
@login_required
def detail(client_id):
    with db_conn() as conn:
        client = _client_in_user_org(conn, client_id, g.user)
        if not client:
            abort(404)
        cases = [dict(r) for r in conn.execute(
            "SELECT * FROM cases WHERE client_id=? ORDER BY created_at DESC", (client_id,)
        ).fetchall()]
        documents = [dict(r) for r in conn.execute("""
            SELECT d.*, u.full_name as uploader_name
            FROM documents d LEFT JOIN users u ON u.id=d.uploaded_by_user_id
            WHERE d.client_id=? ORDER BY d.created_at DESC
        """, (client_id,)).fetchall()]
    return render_template("clients/detail.html",
        current_user=g.user, client=client,
        cases=cases, documents=documents,
    )

@clients_bp.route("/<int:client_id>/edit", methods=["POST"])
@login_required
def edit_client(client_id):
    with db_conn() as conn:
        client = _client_in_user_org(conn, client_id, g.user)
        if not client:
            abort(404)
        if not is_admin_like(g.user):
            flash("You don't have permission to edit this client.", "error")
            return redirect(url_for("clients.detail", client_id=client_id))
        f = request.form
        conn.execute("""
            UPDATE clients SET full_name=?,company_name=?,email=?,phone=?,address=?,notes=?
            WHERE id=?
        """, (f["full_name"], f.get("company_name") or None,
              f.get("email") or None, f.get("phone") or None,
              f.get("address") or None, f.get("notes") or None, client_id))
    return redirect(url_for("clients.detail", client_id=client_id))


# ───────── SETTINGS ─────────
settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

from app.auth_utils import hash_password

@settings_bp.route("")
@login_required
def index():
    # Mask stored API key for display
    raw_key = get_integration_setting("openai_api_key") or ""
    masked_key = ("*" * (len(raw_key) - 4) + raw_key[-4:]) if len(raw_key) > 4 else ("*" * len(raw_key))
    # Gmail status
    try:
        from app.services.gmail_service import gmail_is_configured, gmail_token_exists, _credentials_path, _token_path
        gmail_configured = gmail_is_configured()
        gmail_has_token = gmail_token_exists()
        gmail_creds_path = _credentials_path()
        gmail_token_path = _token_path()
    except Exception:
        gmail_configured = False
        gmail_has_token = False
        gmail_creds_path = "(unavailable)"
        gmail_token_path = "(unavailable)"
    gmail_enabled = get_integration_setting("gmail_enabled") == "1"
    gmail_auto_create = get_integration_setting("gmail_auto_create_clients") == "1"
    return render_template("settings/index.html",
        current_user=g.user,
        openai_key_set=bool(raw_key), openai_key_masked=masked_key,
        gmail_configured=gmail_configured, gmail_has_token=gmail_has_token,
        gmail_creds_path=gmail_creds_path, gmail_token_path=gmail_token_path,
        gmail_enabled=gmail_enabled, gmail_auto_create=gmail_auto_create)


@settings_bp.route("/users")
@login_required
def user_list():
    if g.user["role"] not in ("admin", "owner", "super_admin"):
        abort(403)
    if g.user["role"] == "super_admin":
        # super_admin sees everyone
        q = "SELECT * FROM users ORDER BY full_name"
        params = []
    else:
        # owner/admin: must be scoped to their org; never see super_admin
        org_id = g.user.get("organization_id")
        if not org_id:
            # safety: no org assigned → show only themselves
            q = "SELECT * FROM users WHERE id = ?"
            params = [g.user["id"]]
        else:
            q = "SELECT * FROM users WHERE organization_id = ? AND role != 'super_admin' ORDER BY full_name"
            params = [org_id]
    with db_conn() as conn:
        users = [dict(r) for r in conn.execute(q, params).fetchall()]
    return render_template("settings/users.html", current_user=g.user, users=users)


@settings_bp.route("/ai", methods=["POST"])
@login_required
def save_ai_settings():
    if not is_admin_like(g.user):
        return redirect(url_for("settings.index"))
    api_key = request.form.get("openai_api_key", "").strip()
    if api_key:
        set_integration_setting("openai_api_key", api_key)
    return redirect(url_for("settings.index"))


@settings_bp.route("/gmail/upload", methods=["POST"])
@login_required
def upload_gmail_credentials():
    """Upload Gmail credentials.json and/or token.json files."""
    if not is_admin_like(g.user):
        return redirect(url_for("settings.index"))

    from app.services.gmail_service import _credentials_path, _token_path

    creds_file = request.files.get("credentials_file")
    token_file = request.files.get("token_file")
    saved = []

    if creds_file and creds_file.filename:
        dest = _credentials_path()
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        creds_file.save(dest)
        saved.append("credentials.json")

    if token_file and token_file.filename:
        dest = _token_path()
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        token_file.save(dest)
        saved.append("token.json")

    if saved:
        flash(f"Uploaded: {', '.join(saved)}", "success")
    else:
        flash("No files selected.", "error")

    return redirect(url_for("settings.index") + "#gmail-section")


@settings_bp.route("/gmail/settings", methods=["POST"])
@login_required
def save_gmail_settings():
    """Save Gmail integration toggles."""
    if not is_admin_like(g.user):
        return redirect(url_for("settings.index"))

    enabled = "1" if request.form.get("gmail_enabled") else "0"
    auto_create = "1" if request.form.get("gmail_auto_create_clients") else "0"

    set_integration_setting("gmail_enabled", enabled)
    set_integration_setting("gmail_auto_create_clients", auto_create)

    flash("Gmail settings saved.", "success")
    return redirect(url_for("settings.index") + "#gmail-section")


@settings_bp.route("/gmail/test", methods=["POST"])
@login_required
def test_gmail_connection():
    """Test Gmail API connection."""
    if not is_admin_like(g.user):
        return redirect(url_for("settings.index"))

    try:
        from app.services.gmail_service import get_gmail_service
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        flash(f"Gmail connection OK. Connected as: {email}", "success")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Gmail connection test failed: %s", e)
        flash("Gmail connection failed. Check your credentials in the settings.", "error")

    return redirect(url_for("settings.index") + "#gmail-section")


@settings_bp.route("/users/new", methods=["GET","POST"])
@login_required
def new_user():
    if not is_admin_like(g.user):
        return redirect(url_for("settings.index"))
    error = None
    if request.method == "POST":
        f = request.form
        with db_conn() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email=?", (f["email"].lower().strip(),)).fetchone()
            if existing:
                error = "Email already in use"
            else:
                new_lang = f.get("language", "en")
                if new_lang not in ("en", "es", "it", "ja", "pt"):
                    new_lang = "en"
                new_role = f.get("role", "staff")
                # Only super_admin can create super_admin users
                if new_role == "super_admin" and g.user["role"] != "super_admin":
                    new_role = "staff"
                # super_admin users have no org; all others inherit the creating admin's org
                if new_role == "super_admin":
                    new_org_id = None
                elif g.user["role"] == "super_admin" and new_role == "owner":
                    # Auto-create a new organization for this owner
                    import re as _re
                    org_name = f.get("organization_name", "").strip() or (f["full_name"] + "'s Organization")
                    slug = _re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-")
                    cur_org = conn.execute(
                        "INSERT INTO organizations (name, slug, plan, status, is_active) VALUES (?,?,?,?,?)",
                        (org_name, slug, "trial", "active", 1)
                    )
                    new_org_id = cur_org.lastrowid
                else:
                    new_org_id = org_id_for(g.user)
                conn.execute("""
                    INSERT INTO users (full_name, email, hashed_password, role, job_title, phone, avatar_color, is_active, language, organization_id)
                    VALUES (?,?,?,?,?,?,?,1,?,?)
                """, (f["full_name"], f["email"].lower().strip(),
                      hash_password(f["password"]),
                      new_role,
                      f.get("job_title") or None,
                      f.get("phone") or None,
                      f.get("avatar_color","#6366f1"),
                      new_lang, new_org_id))
                return redirect(url_for("settings.user_list"))
    return render_template("settings/user_form.html", current_user=g.user, user=None, error=error)

@settings_bp.route("/users/<int:user_id>/edit", methods=["GET","POST"])
@login_required
def edit_user(user_id):
    if not is_admin_like(g.user):
        return redirect(url_for("settings.index"))
    with db_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            abort(404)
        user = dict(user)

        # Non-super-admin cannot edit users outside their own org or super_admin users
        if g.user["role"] != "super_admin":
            if user["role"] == "super_admin":
                abort(403)
            if user.get("organization_id") != g.user.get("organization_id"):
                abort(403)

        if request.method == "POST":
            f = request.form
            is_active = 1 if f.get("is_active") == "on" else 0
            new_role = f.get("role", "staff")
            edit_lang = f.get("language", user.get("language") or "en")
            if edit_lang not in ("en", "es", "it", "ja", "pt"):
                edit_lang = "en"

            # --- Last super_admin protection ---
            if user["role"] == "super_admin" and (new_role != "super_admin" or not is_active):
                sa_count = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role='super_admin' AND is_active=1"
                ).fetchone()[0]
                if sa_count <= 1:
                    flash("Cannot demote or deactivate the last super admin.", "error")
                    return render_template("settings/user_form.html", current_user=g.user, user=user, error="Cannot demote or deactivate the last super admin.")

            # Only super_admin can assign/keep the super_admin role
            if new_role == "super_admin" and g.user["role"] != "super_admin":
                new_role = user["role"]

            # Normalize organization_id based on role
            if new_role == "super_admin":
                # super_admin must not belong to any tenant org
                new_org_id = None
            elif user["role"] == "super_admin" and new_role != "super_admin":
                # Demoted from super_admin — assign to the editing admin's org
                new_org_id = g.user.get("organization_id")
            else:
                new_org_id = user.get("organization_id")

            if f.get("new_password"):
                conn.execute("""
                    UPDATE users SET full_name=?,email=?,role=?,job_title=?,phone=?,
                        avatar_color=?,is_active=?,language=?,hashed_password=?,organization_id=? WHERE id=?
                """, (f["full_name"], f["email"].lower().strip(),
                      new_role, f.get("job_title") or None,
                      f.get("phone") or None, f.get("avatar_color","#6366f1"),
                      is_active, edit_lang, hash_password(f["new_password"]), new_org_id, user_id))
            else:
                conn.execute("""
                    UPDATE users SET full_name=?,email=?,role=?,job_title=?,phone=?,
                        avatar_color=?,is_active=?,language=?,organization_id=? WHERE id=?
                """, (f["full_name"], f["email"].lower().strip(),
                      new_role, f.get("job_title") or None,
                      f.get("phone") or None, f.get("avatar_color","#6366f1"),
                      is_active, edit_lang, new_org_id, user_id))
            return redirect(url_for("settings.user_list"))
    return render_template("settings/user_form.html", current_user=g.user, user=user, error=None)

@settings_bp.route("/profile/edit", methods=["POST"])
@login_required
def edit_profile():
    f = request.form
    lang = f.get("language", "en")
    if lang not in ("en", "es", "it", "ja", "pt"):
        lang = "en"
    with db_conn() as conn:
        if f.get("new_password"):
            conn.execute("""
                UPDATE users SET full_name=?,job_title=?,phone=?,language=?,hashed_password=? WHERE id=?
            """, (f["full_name"], f.get("job_title") or None,
                  f.get("phone") or None, lang, hash_password(f["new_password"]), g.user["id"]))
        else:
            conn.execute("""
                UPDATE users SET full_name=?,job_title=?,phone=?,language=? WHERE id=?
            """, (f["full_name"], f.get("job_title") or None,
                  f.get("phone") or None, lang, g.user["id"]))
    return redirect(url_for("settings.index"))


# ───────── FINANCES ─────────
finances_bp = Blueprint("finances", __name__, url_prefix="/finances")

# Static mock financial data — two example matters
_MOCK_CASES = [
    {
        "id": 1,
        "title": "J. Moretti vs. Greenfield",
        "client": "J. Moretti",
        "status": "active",
        "priority": "high",
        "matter_type": "Litigation",
        "billed_total": 48_500.00,
        "collected": 36_000.00,
        "retainer_deposited": 20_000.00,
        "retainer_remaining": 4_250.00,
        "next_billing_date": "2026-04-01",
        "hours_logged": 124.5,
        "outcome": None,
        "at_risk": True,
        "staff_hours": [
            {"name": "Marco Rossi",    "hours": 54.0},
            {"name": "Elena Bianchi",  "hours": 42.5},
            {"name": "Lucia Ferri",    "hours": 28.0},
        ],
        "monthly_billing": [2400, 3100, 5800, 7200, 6500, 8100, 4200, 3900, 4300, 3000, 0, 0],
    },
    {
        "id": 2,
        "title": "Acme Corp. Merger",
        "client": "Acme Corp.",
        "status": "active",
        "priority": "medium",
        "matter_type": "Corporate M&A",
        "billed_total": 112_000.00,
        "collected": 112_000.00,
        "retainer_deposited": 50_000.00,
        "retainer_remaining": 18_750.00,
        "next_billing_date": "2026-03-28",
        "hours_logged": 287.0,
        "outcome": None,
        "at_risk": False,
        "staff_hours": [
            {"name": "Marco Rossi",    "hours": 110.0},
            {"name": "Sofia Conti",    "hours": 97.0},
            {"name": "Elena Bianchi",  "hours": 80.0},
        ],
        "monthly_billing": [8000, 9500, 11200, 10800, 12400, 14100, 13200, 11800, 10900, 9600, 0, 0],
    },
    {
        "id": 3,
        "title": "Rivera Estate Settlement",
        "client": "D. Rivera",
        "status": "closed",
        "priority": "low",
        "matter_type": "Estate & Probate",
        "billed_total": 22_000.00,
        "collected": 22_000.00,
        "retainer_deposited": 10_000.00,
        "retainer_remaining": 0.00,
        "next_billing_date": None,
        "hours_logged": 68.0,
        "outcome": "won",
        "at_risk": False,
        "staff_hours": [
            {"name": "Lucia Ferri",    "hours": 40.0},
            {"name": "Marco Rossi",    "hours": 28.0},
        ],
        "monthly_billing": [1200, 2100, 3400, 4800, 5200, 5300, 0, 0, 0, 0, 0, 0],
    },
    {
        "id": 4,
        "title": "Hernandez v. City of Naples",
        "client": "P. Hernandez",
        "status": "closed",
        "priority": "high",
        "matter_type": "Civil Rights",
        "billed_total": 67_300.00,
        "collected": 55_000.00,
        "retainer_deposited": 15_000.00,
        "retainer_remaining": 0.00,
        "next_billing_date": None,
        "hours_logged": 198.0,
        "outcome": "lost",
        "at_risk": False,
        "staff_hours": [
            {"name": "Elena Bianchi",  "hours": 95.0},
            {"name": "Marco Rossi",    "hours": 68.0},
            {"name": "Sofia Conti",    "hours": 35.0},
        ],
        "monthly_billing": [3200, 5100, 7800, 9400, 11200, 12600, 10900, 7100, 0, 0, 0, 0],
    },
]

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

@finances_bp.route("")
@login_required
def index():
    if not is_admin_like(g.user):
        return redirect(url_for("dashboard.index"))

    status_filter = request.args.get("status", "all")
    priority_filter = request.args.get("priority", "all")

    cases = _MOCK_CASES
    if status_filter != "all":
        cases = [c for c in cases if c["status"] == status_filter]
    if priority_filter != "all":
        cases = [c for c in cases if c["priority"] == priority_filter]

    # Summary KPIs (always over full dataset)
    all_cases = _MOCK_CASES
    total_billed      = sum(c["billed_total"] for c in all_cases)
    total_collected   = sum(c["collected"]    for c in all_cases)
    total_outstanding = total_billed - total_collected
    total_retainer    = sum(c["retainer_remaining"] for c in all_cases)
    active_cases      = [c for c in all_cases if c["status"] == "active"]
    closed_cases      = [c for c in all_cases if c["status"] == "closed"]
    won  = sum(1 for c in closed_cases if c["outcome"] == "won")
    lost = sum(1 for c in closed_cases if c["outcome"] == "lost")
    win_rate = round(won / (won + lost) * 100) if (won + lost) > 0 else 0
    at_risk_count = sum(1 for c in active_cases if c["at_risk"])

    # Aggregate monthly billing (all cases, for chart)
    monthly_totals = [0] * 12
    for c in all_cases:
        for i, v in enumerate(c["monthly_billing"]):
            monthly_totals[i] += v

    # Q1/Q2/Q3/Q4 totals
    quarters = [
        sum(monthly_totals[0:3]),
        sum(monthly_totals[3:6]),
        sum(monthly_totals[6:9]),
        sum(monthly_totals[9:12]),
    ]

    # Staff hours aggregated across all cases
    staff_map: dict = {}
    for c in all_cases:
        for sh in c["staff_hours"]:
            staff_map[sh["name"]] = staff_map.get(sh["name"], 0) + sh["hours"]
    staff_hours = sorted(staff_map.items(), key=lambda x: -x[1])

    return render_template("finances/index.html",
        current_user=g.user,
        cases=cases,
        all_cases=all_cases,
        total_billed=total_billed,
        total_collected=total_collected,
        total_outstanding=total_outstanding,
        total_retainer=total_retainer,
        win_rate=win_rate,
        at_risk_count=at_risk_count,
        monthly_totals=monthly_totals,
        months=_MONTHS,
        quarters=quarters,
        staff_hours=staff_hours,
        status_filter=status_filter,
        priority_filter=priority_filter,
        active_count=len(active_cases),
        closed_count=len(closed_cases),
    )


# ───────── LOGIN DASHBOARD ─────────
logins_bp = Blueprint("logins", __name__, url_prefix="/logins")

# Mock check-in seed data — shown when no real records exist for an employee
_MOCK_CHECKINS = {
    "Marco Rossi": [
        {"checked_in_at": "2026-03-17 08:55:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-16 09:04:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-15 09:31:00", "status": "late",    "notes": "Train delay"},
        {"checked_in_at": "2026-03-14 08:48:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-13 08:51:00", "status": "on_time", "notes": ""},
    ],
    "Elena Bianchi": [
        {"checked_in_at": "2026-03-17 10:12:00", "status": "late",    "notes": "Doctor appointment"},
        {"checked_in_at": "2026-03-16 09:00:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-15 09:03:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-14 09:47:00", "status": "late",    "notes": "Traffic"},
        {"checked_in_at": "2026-03-13 08:59:00", "status": "on_time", "notes": ""},
    ],
    "Lucia Ferri": [
        {"checked_in_at": "2026-03-17 08:45:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-16 08:50:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-15 11:20:00", "status": "exception", "notes": "Court appearance AM"},
        {"checked_in_at": "2026-03-14 08:52:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-13 09:01:00", "status": "on_time", "notes": ""},
    ],
    "Sofia Conti": [
        {"checked_in_at": "2026-03-17 09:00:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-16 09:00:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-15 09:00:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-14 09:00:00", "status": "on_time", "notes": ""},
        {"checked_in_at": "2026-03-13 09:00:00", "status": "on_time", "notes": ""},
    ],
}

_MOCK_HOURS = {
    "Marco Rossi":  {"week": 42.0, "cases": "J. Moretti vs. Greenfield, Acme Corp. Merger",  "focus": "Trial prep"},
    "Elena Bianchi":{"week": 38.5, "cases": "Hernandez v. City of Naples, J. Moretti",         "focus": "Brief drafting"},
    "Lucia Ferri":  {"week": 31.0, "cases": "Rivera Estate Settlement",                         "focus": "Discovery review"},
    "Sofia Conti":  {"week": 45.5, "cases": "Acme Corp. Merger",                                "focus": "Due diligence"},
}


def _build_ai_prompt(employee_data: list) -> str:
    lines = ["You are an office operations analyst for a law firm."]
    lines.append("Below is a summary of employee check-in behaviour and workload for the past week.")
    lines.append("Provide a concise 3-4 paragraph analysis covering:")
    lines.append("1. Overall punctuality patterns and any concerns.")
    lines.append("2. Workload balance — flag overloaded or underutilised staff.")
    lines.append("3. At-risk indicators (frequent late arrivals + heavy caseload).")
    lines.append("4. Suggested follow-up actions for management.")
    lines.append("Keep the tone professional and objective. Do not repeat raw numbers — interpret them.\n")
    for emp in employee_data:
        u = emp["user"]
        lines.append(f"Employee: {u['full_name']} ({u.get('job_title') or u['role']})")
        lines.append(f"  Hours this week: {emp['week_hours']}h")
        lines.append(f"  Check-ins this week: {emp['total_checkins']} total — "
                     f"{emp['on_time']} on-time, {emp['late']} late, {emp['exception']} exception")
        lines.append(f"  Current cases: {emp['cases_focus']}")
        if u.get("hourly_rate"):
            lines.append(f"  Hourly rate: ${u['hourly_rate']:.0f}/h — weekly cost: ${emp['week_cost']:.0f}")
        lines.append("")
    return "\n".join(lines)


@logins_bp.route("")
@login_required
def index():
    if not is_admin_like(g.user):
        return redirect(url_for("dashboard.index"))

    import requests as http_requests

    now_dt = datetime.utcnow()
    week_start = (now_dt - timedelta(days=now_dt.weekday())).replace(hour=0, minute=0, second=0)
    week_start_str = week_start.strftime("%Y-%m-%d %H:%M:%S")
    fourteen_ago = (now_dt - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    lu, lp = org_filter(g.user)
    with db_conn() as conn:
        users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1{lu} ORDER BY full_name", lp
        ).fetchall()]

        # --- Batch queries to avoid N+1 ---
        # All check-ins since 14 days ago (covers both week and timeline needs)
        lc, lcp = org_filter(g.user)
        all_checkins = [dict(r) for r in conn.execute(
            f"""SELECT id, user_id, checked_in_at, status, notes, source FROM checkins
            WHERE checked_in_at >= ?{lc}
            ORDER BY checked_in_at DESC""",
            [fourteen_ago] + lcp
        ).fetchall()]

        # Last check-in per user (single query)
        last_checkins_rows = conn.execute("""
            SELECT c1.user_id, c1.checked_in_at, c1.status
            FROM checkins c1
            INNER JOIN (
                SELECT user_id, MAX(checked_in_at) as max_at
                FROM checkins GROUP BY user_id
            ) c2 ON c1.user_id = c2.user_id AND c1.checked_in_at = c2.max_at
        """).fetchall()
        last_checkin_map = {r["user_id"]: dict(r) for r in last_checkins_rows}

        # Active case counts per user (single query)
        case_counts_rows = conn.execute("""
            SELECT ca.user_id, COUNT(*) as cnt
            FROM case_assignments ca
            JOIN cases c ON c.id = ca.case_id
            WHERE c.status != 'closed'
            GROUP BY ca.user_id
        """).fetchall()
        case_count_map = {r["user_id"]: r["cnt"] for r in case_counts_rows}

        # Index check-ins by user_id
        from collections import defaultdict
        checkins_by_user = defaultdict(list)
        for ci in all_checkins:
            checkins_by_user[ci["user_id"]].append(ci)

        employee_data = []
        for u in users:
            uid = u["id"]
            user_cis = checkins_by_user.get(uid, [])

            # Week check-ins (already sorted DESC)
            week_cis = [c for c in user_cis if c["checked_in_at"] >= week_start_str]

            # Timeline: recent 14-day, limit 10
            timeline_real = user_cis[:10]

            active_cases = case_count_map.get(uid, 0)

            # Merge with mock data if no real records exist
            mock = _MOCK_CHECKINS.get(u["full_name"], [])
            mock_hours = _MOCK_HOURS.get(u["full_name"], {"week": 0, "cases": "—", "focus": "—"})

            if week_cis:
                display_cis = week_cis
                week_hours = round(active_cases * 8.0, 1)  # rough estimate from real data
            else:
                display_cis = mock
                week_hours = mock_hours["week"]

            timeline_cis = timeline_real if timeline_real else mock[:5]

            # Aggregate status counts from whichever source we have
            source_cis = display_cis
            on_time_ct  = sum(1 for c in source_cis if c["status"] == "on_time")
            late_ct     = sum(1 for c in source_cis if c["status"] == "late")
            exc_ct      = sum(1 for c in source_cis if c["status"] == "exception")
            total_ct    = len(source_cis)

            last_checkin_display = None
            last_checkin_status  = None
            last_ci = last_checkin_map.get(uid)
            if last_ci:
                last_checkin_display = last_ci["checked_in_at"]
                last_checkin_status  = last_ci["status"]
            elif mock:
                last_checkin_display = mock[0]["checked_in_at"]
                last_checkin_status  = mock[0]["status"]

            hourly_rate = u.get("hourly_rate") or 0
            week_cost   = round(week_hours * hourly_rate, 2)

            # Determine risk flag
            at_risk = (late_ct >= 2 and active_cases >= 2) or week_hours > 44

            cases_focus = mock_hours["cases"] if not week_cis else f"{active_cases} active matter(s)"

            employee_data.append({
                "user":              u,
                "week_hours":        week_hours,
                "week_cost":         week_cost,
                "hourly_rate":       hourly_rate,
                "total_checkins":    total_ct,
                "on_time":           on_time_ct,
                "late":              late_ct,
                "exception":         exc_ct,
                "last_checkin":      last_checkin_display,
                "last_checkin_status": last_checkin_status,
                "timeline_cis":      timeline_cis,
                "active_cases":      active_cases,
                "cases_focus":       cases_focus,
                "at_risk":           at_risk,
            })

    # Sort: at-risk first, then by week_hours desc
    employee_data.sort(key=lambda e: (-int(e["at_risk"]), -e["week_hours"]))

    # Max hours for bar chart scaling
    max_hours = max((e["week_hours"] for e in employee_data), default=1) or 1

    # AI summary (best-effort — no crash if key missing or API fails)
    ai_summary = None
    ai_error   = None
    api_key = get_integration_setting("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            prompt = _build_ai_prompt(employee_data)
            resp = http_requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 600,
                },
                timeout=20,
            )
            if resp.ok:
                ai_summary = resp.json()["choices"][0]["message"]["content"].strip()
            else:
                ai_error = f"OpenAI API error {resp.status_code}"
        except Exception as exc:
            ai_error = f"Could not reach OpenAI: {exc}"
    else:
        ai_error = "No API key configured. Add it in Settings → AI Integrations."

    return render_template("logins/index.html",
        current_user=g.user,
        employee_data=employee_data,
        max_hours=max_hours,
        ai_summary=ai_summary,
        ai_error=ai_error,
        week_start=week_start,
        now=now_dt,
    )


@logins_bp.route("/add-checkin/<int:user_id>", methods=["POST"])
@login_required
def add_checkin(user_id):
    if not is_admin_like(g.user):
        return redirect(url_for("logins.index"))
    status = request.form.get("status", "on_time")
    if status not in ("on_time", "late", "exception"):
        status = "on_time"
    notes = request.form.get("notes", "").strip() or None
    checked_in_at = request.form.get("checked_in_at", "").strip()
    if not checked_in_at:
        checked_in_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    else:
        # Validate admin-supplied datetime
        try:
            datetime.strptime(checked_in_at, "%Y-%m-%dT%H:%M")
            checked_in_at = checked_in_at.replace("T", " ") + ":00"
        except ValueError:
            checked_in_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with db_conn() as conn:
        conn.execute("""
            INSERT INTO checkins (user_id, checked_in_at, status, notes, source)
            VALUES (?, ?, ?, ?, 'admin')
        """, (user_id, checked_in_at, status, notes))
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (g.user["id"], "checkin_admin_created",
              f"Admin added check-in for user {user_id}: status={status}, at={checked_in_at}, notes={notes or ''}"))
    flash("Check-in entry added.", "success")
    return redirect(url_for("logins.index"))


@logins_bp.route("/delete-checkin/<int:checkin_id>", methods=["POST"])
@login_required
def delete_checkin(checkin_id):
    if not is_admin_like(g.user):
        return redirect(url_for("logins.index"))
    with db_conn() as conn:
        # Fetch details before deleting for audit trail
        ci = conn.execute(
            "SELECT id, user_id, checked_in_at, status, notes FROM checkins WHERE id=?",
            (checkin_id,)
        ).fetchone()
        if ci:
            ci = dict(ci)
            conn.execute("DELETE FROM checkins WHERE id=?", (checkin_id,))
            conn.execute("""
                INSERT INTO activity_logs (user_id, action, details, created_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (g.user["id"], "checkin_deleted",
                  f"Deleted check-in #{checkin_id} for user {ci['user_id']}: "
                  f"status={ci['status']}, at={ci['checked_in_at']}, notes={ci.get('notes') or ''}"))
            flash("Check-in entry deleted.", "success")
        else:
            flash("Check-in entry not found.", "error")
    return redirect(url_for("logins.index"))


@logins_bp.route("/set-rate/<int:user_id>", methods=["POST"])
@login_required
def set_rate(user_id):
    if not is_admin_like(g.user):
        return redirect(url_for("logins.index"))
    try:
        rate = float(request.form.get("hourly_rate", 0))
        rate = max(0, rate)
    except (ValueError, TypeError):
        rate = 0
    with db_conn() as conn:
        conn.execute("UPDATE users SET hourly_rate=? WHERE id=?", (rate, user_id))
    return redirect(url_for("logins.index"))
