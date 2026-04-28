from flask import Blueprint, render_template, request, redirect, url_for, g, abort
from app.auth_utils import login_required, get_current_user, org_filter, org_id_for
from app.database import db_conn
from datetime import datetime

bp = Blueprint("cases", __name__, url_prefix="/cases")

def log_activity(conn, user_id, case_id, action, details=None, organization_id=None):
    conn.execute(
        "INSERT INTO activity_logs (user_id, case_id, action, details, organization_id) VALUES (?,?,?,?,?)",
        (user_id, case_id, action, details, organization_id)
    )


def _case_in_user_org(conn, case_id, user):
    """Return the case row dict if it exists AND belongs to user's org (or user is super_admin), else None."""
    row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not row:
        return None
    if user.get("role") == "super_admin":
        return dict(row)
    if row["organization_id"] != user.get("organization_id"):
        return None
    return dict(row)

@bp.route("")
@login_required
def board():
    statuses = ["open", "litigation", "closed"]
    # legacy db values that map to "litigation"
    LITIGATION_DB = ("litigation", "in_progress", "waiting")
    cases_by_status = {}
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    oc, op = org_filter(g.user, alias="c")

    with db_conn() as conn:
        for s in statuses:
            if s == "litigation":
                placeholders = ",".join("?" * len(LITIGATION_DB))
                base = f"""
                    SELECT c.*, cl.full_name as client_name
                    FROM cases c
                    LEFT JOIN clients cl ON cl.id=c.client_id
                    {{join}}
                    WHERE c.status IN ({placeholders}){oc}
                    ORDER BY c.created_at DESC
                """
                if g.user["role"] == "staff":
                    rows = conn.execute(
                        base.format(join="JOIN case_assignments ca ON ca.case_id=c.id AND ca.user_id=?"),
                        [g.user["id"]] + list(LITIGATION_DB) + op
                    ).fetchall()
                else:
                    rows = conn.execute(
                        base.format(join=""),
                        list(LITIGATION_DB) + op
                    ).fetchall()
            else:
                if g.user["role"] == "staff":
                    rows = conn.execute(
                        f"""SELECT c.*, cl.full_name as client_name
                        FROM cases c
                        LEFT JOIN clients cl ON cl.id=c.client_id
                        JOIN case_assignments ca ON ca.case_id=c.id AND ca.user_id=?
                        WHERE c.status=?{oc}
                        ORDER BY c.created_at DESC""",
                        [g.user["id"], s] + op
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""SELECT c.*, cl.full_name as client_name
                        FROM cases c
                        LEFT JOIN clients cl ON cl.id=c.client_id
                        WHERE c.status=?{oc}
                        ORDER BY c.created_at DESC""",
                        [s] + op
                    ).fetchall()

            cases_list = []
            for row in rows:
                case = dict(row)
                # normalise legacy statuses for display
                if case["status"] in ("in_progress", "waiting"):
                    case["status"] = "litigation"
                assignees = conn.execute("""
                    SELECT u.id, u.full_name, u.avatar_color
                    FROM case_assignments ca JOIN users u ON u.id=ca.user_id
                    WHERE ca.case_id=?
                """, (case["id"],)).fetchall()
                case["assignees"] = [dict(a) for a in assignees]
                cases_list.append(case)
            cases_by_status[s] = cases_list

    return render_template("cases/board.html",
        current_user=g.user,
        cases_by_status=cases_by_status,
        now=now,
    )

@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_case():
    if g.user["role"] not in ("admin", "owner", "super_admin"):
        return redirect(url_for("cases.board"))

    uc, up = org_filter(g.user)
    with db_conn() as conn:
        clients = conn.execute(
            f"SELECT * FROM clients WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()
        users = conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()

    if request.method == "POST":
        f = request.form
        due_date = f.get("due_date") or None
        oid = org_id_for(g.user)
        with db_conn() as conn:
            cur = conn.execute("""
                INSERT INTO cases (title, description, client_id, priority, status,
                    due_date, overview, current_step, next_action, blockers,
                    court_name, case_number, case_type, organization_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                f["title"], f.get("description", ""),
                f.get("client_id") or None,
                f.get("priority", "medium"), f.get("status", "open"),
                due_date,
                f.get("overview", ""), f.get("current_step", ""),
                f.get("next_action", ""), f.get("blockers", ""),
                f.get("court_name", "") or None, f.get("case_number", "") or None,
                f.get("case_type", "Other") or "Other",
                oid,
            ))
            case_id = cur.lastrowid
            raw_ids = request.form.getlist("assigned_users")
            parsed_ids = []
            for uid_str in raw_ids:
                try:
                    parsed_ids.append(int(uid_str))
                except (ValueError, TypeError):
                    pass
            if parsed_ids:
                ph = ",".join("?" * len(parsed_ids))
                oc, op = org_filter(g.user)
                valid_rows = conn.execute(
                    f"SELECT id FROM users WHERE id IN ({ph}){oc}", parsed_ids + op
                ).fetchall()
                valid_ids = {r["id"] for r in valid_rows}
                for uid in parsed_ids:
                    if uid in valid_ids:
                        conn.execute(
                            "INSERT OR IGNORE INTO case_assignments (case_id, user_id) VALUES (?,?)",
                            (case_id, uid)
                        )
            log_activity(conn, g.user["id"], case_id, "Case created", f"Status: {f.get('status','open')}", organization_id=oid)
        return redirect(url_for("cases.detail", case_id=case_id))

    return render_template("cases/form.html",
        current_user=g.user,
        clients=[dict(c) for c in clients],
        users=[dict(u) for u in users],
        case=None,
    )

@bp.route("/<int:case_id>")
@login_required
def detail(case_id):
    with db_conn() as conn:
        oc, op = org_filter(g.user, alias="c")
        case = conn.execute(f"""
            SELECT c.*, cl.full_name as client_name, cl.id as client_id
            FROM cases c LEFT JOIN clients cl ON cl.id=c.client_id
            WHERE c.id=?{oc}
        """, [case_id] + op).fetchone()
        if not case:
            abort(404)
        case = dict(case)
        if case["status"] in ("in_progress", "waiting"):
            case["status"] = "litigation"

        assignees = conn.execute("""
            SELECT u.* FROM case_assignments ca JOIN users u ON u.id=ca.user_id WHERE ca.case_id=?
        """, (case_id,)).fetchall()
        case["assignees"] = [dict(a) for a in assignees]
        assigned_ids = [a["id"] for a in case["assignees"]]

        if g.user["role"] == "staff" and g.user["id"] not in assigned_ids:
            abort(403)

        can_edit = g.user["role"] == "admin" or (
            g.user["role"] == "staff" and g.user["id"] in assigned_ids
        )

        tasks = conn.execute("""
            SELECT t.*, u.full_name as assignee_name
            FROM tasks t LEFT JOIN users u ON u.id=t.assigned_to_user_id
            WHERE t.case_id=? ORDER BY t.created_at DESC
        """, (case_id,)).fetchall()

        documents = conn.execute("""
            SELECT d.*, u.full_name as uploader_name
            FROM documents d LEFT JOIN users u ON u.id=d.uploaded_by_user_id
            WHERE d.case_id=? ORDER BY d.created_at DESC
        """, (case_id,)).fetchall()

        activity = conn.execute("""
            SELECT al.*, u.full_name as user_name, u.avatar_color
            FROM activity_logs al LEFT JOIN users u ON u.id=al.user_id
            WHERE al.case_id=? ORDER BY al.created_at DESC LIMIT 30
        """, (case_id,)).fetchall()

        uc2, up2 = org_filter(g.user)
        all_users = conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc2} ORDER BY full_name", up2
        ).fetchall()
        all_clients = conn.execute(
            f"SELECT * FROM clients WHERE is_active=1{uc2} ORDER BY full_name", up2
        ).fetchall()

        key_dates = conn.execute("""
            SELECT * FROM appointments
            WHERE case_id=? AND appointment_type='case_key_date'
            ORDER BY start_datetime ASC
        """, (case_id,)).fetchall()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("cases/detail.html",
        current_user=g.user, case=case,
        can_edit=can_edit,
        tasks=[dict(t) for t in tasks],
        documents=[dict(d) for d in documents],
        activity=[dict(a) for a in activity],
        all_users=[dict(u) for u in all_users],
        all_clients=[dict(c) for c in all_clients],
        key_dates=[dict(k) for k in key_dates],
        now=now,
    )

@bp.route("/<int:case_id>/edit", methods=["POST"])
@login_required
def edit_case(case_id):
    with db_conn() as conn:
        case_row = _case_in_user_org(conn, case_id, g.user)
        if not case_row:
            abort(404)
        assignments = conn.execute("SELECT * FROM case_assignments WHERE case_id=?", (case_id,)).fetchall()
        assigned_ids = [a["user_id"] for a in assignments]

    can_edit = g.user["role"] in ("admin", "owner", "super_admin") or (
        g.user["role"] == "staff" and g.user["id"] in assigned_ids
    )
    if not can_edit:
        abort(403)

    f = request.form
    with db_conn() as conn:
        old = conn.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()
        new_status = f.get("status", "open")
        closed_at = "datetime('now')" if new_status == "closed" and old and old["status"] != "closed" else None

        court_name = f.get("court_name", "") or None
        case_number = f.get("case_number", "") or None
        case_type = f.get("case_type", "Other") or "Other"
        if closed_at:
            conn.execute("""
                UPDATE cases SET title=?,description=?,client_id=?,priority=?,status=?,
                    due_date=?,overview=?,current_step=?,next_action=?,blockers=?,
                    court_name=?,case_number=?,case_type=?,
                    closed_at=datetime('now'), updated_at=datetime('now') WHERE id=?
            """, (f["title"], f.get("description",""), f.get("client_id") or None,
                  f.get("priority","medium"), new_status,
                  f.get("due_date") or None,
                  f.get("overview",""), f.get("current_step",""),
                  f.get("next_action",""), f.get("blockers",""),
                  court_name, case_number, case_type, case_id))
        else:
            conn.execute("""
                UPDATE cases SET title=?,description=?,client_id=?,priority=?,status=?,
                    due_date=?,overview=?,current_step=?,next_action=?,blockers=?,
                    court_name=?,case_number=?,case_type=?,
                    updated_at=datetime('now') WHERE id=?
            """, (f["title"], f.get("description",""), f.get("client_id") or None,
                  f.get("priority","medium"), new_status,
                  f.get("due_date") or None,
                  f.get("overview",""), f.get("current_step",""),
                  f.get("next_action",""), f.get("blockers",""),
                  court_name, case_number, case_type, case_id))

        if g.user["role"] in ("admin", "owner", "super_admin"):
            conn.execute("DELETE FROM case_assignments WHERE case_id=?", (case_id,))
            raw_ids = request.form.getlist("assigned_users")
            parsed_ids = []
            for uid_str in raw_ids:
                try:
                    parsed_ids.append(int(uid_str))
                except (ValueError, TypeError):
                    pass
            if parsed_ids:
                ph = ",".join("?" * len(parsed_ids))
                oc, op = org_filter(g.user)
                valid_rows = conn.execute(
                    f"SELECT id FROM users WHERE id IN ({ph}){oc}", parsed_ids + op
                ).fetchall()
                valid_ids = {r["id"] for r in valid_rows}
                for uid in parsed_ids:
                    if uid in valid_ids:
                        conn.execute(
                            "INSERT OR IGNORE INTO case_assignments (case_id,user_id) VALUES (?,?)",
                            (case_id, uid)
                        )

        oid = case_row.get("organization_id")
        if old and old["status"] != new_status:
            log_activity(conn, g.user["id"], case_id, "Status changed", f"{old['status']} → {new_status}", organization_id=oid)
        else:
            log_activity(conn, g.user["id"], case_id, "Case updated", organization_id=oid)

    return redirect(url_for("cases.detail", case_id=case_id))

@bp.route("/<int:case_id>/key-dates/new", methods=["POST"])
@login_required
def add_key_date(case_id):
    with db_conn() as conn:
        case = _case_in_user_org(conn, case_id, g.user)
        if not case:
            abort(404)
        assigned_ids = [a["user_id"] for a in conn.execute(
            "SELECT user_id FROM case_assignments WHERE case_id=?", (case_id,)).fetchall()]
    can_edit = g.user["role"] in ("admin", "owner", "super_admin") or (g.user["role"] == "staff" and g.user["id"] in assigned_ids)
    if not can_edit:
        abort(403)

    f = request.form
    date = f.get("date") or None
    start_time = f.get("start_time") or "00:00"
    end_time = f.get("end_time") or "00:00"
    start_dt = f"{date} {start_time}:00" if date else None
    end_dt = f"{date} {end_time}:00" if date else None
    oid = org_id_for(g.user) or case.get("organization_id")

    with db_conn() as conn:
        conn.execute("""
            INSERT INTO appointments
                (title, start_datetime, end_datetime, case_id, location,
                 appointment_type, created_by_user_id, description, organization_id)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            f["title"], start_dt, end_dt, case_id,
            f.get("location") or None,
            "case_key_date",
            g.user["id"],
            f.get("kd_type") or None,
            oid,
        ))
        log_activity(conn, g.user["id"], case_id, "Key date added", f["title"], organization_id=oid)
    return redirect(url_for("cases.detail", case_id=case_id))


@bp.route("/<int:case_id>/key-dates/<int:appt_id>/delete", methods=["POST"])
@login_required
def delete_key_date(case_id, appt_id):
    with db_conn() as conn:
        case = _case_in_user_org(conn, case_id, g.user)
        if not case:
            abort(404)
        assigned_ids = [a["user_id"] for a in conn.execute(
            "SELECT user_id FROM case_assignments WHERE case_id=?", (case_id,)).fetchall()]
    can_edit = g.user["role"] in ("admin", "owner", "super_admin") or (g.user["role"] == "staff" and g.user["id"] in assigned_ids)
    if not can_edit:
        abort(403)

    with db_conn() as conn:
        appt = conn.execute(
            "SELECT id FROM appointments WHERE id=? AND case_id=? AND appointment_type='case_key_date'",
            (appt_id, case_id)).fetchone()
        if appt:
            conn.execute("DELETE FROM appointments WHERE id=?", (appt_id,))
            log_activity(conn, g.user["id"], case_id, "Key date deleted", organization_id=case.get("organization_id"))
    return redirect(url_for("cases.detail", case_id=case_id))


@bp.route("/<int:case_id>/tasks/new", methods=["POST"])
@login_required
def add_task(case_id):
    with db_conn() as conn:
        case = _case_in_user_org(conn, case_id, g.user)
        if not case:
            abort(404)
        assigned_ids = [a["user_id"] for a in conn.execute(
            "SELECT user_id FROM case_assignments WHERE case_id=?", (case_id,)).fetchall()]
    can_edit = g.user["role"] in ("admin", "owner", "super_admin") or (g.user["role"] == "staff" and g.user["id"] in assigned_ids)
    if not can_edit:
        abort(403)

    f = request.form
    due_date = f.get("due_date") or None
    oid = org_id_for(g.user) or case.get("organization_id")
    with db_conn() as conn:
        conn.execute("""
            INSERT INTO tasks (title, description, case_id, assigned_to_user_id,
                due_date, priority, created_by_user_id, organization_id)
            VALUES (?,?,?,?,?,?,?,?)
        """, (f["title"], f.get("description",""), case_id,
              f.get("assigned_to") or None, due_date,
              f.get("priority","medium"), g.user["id"], oid))
        log_activity(conn, g.user["id"], case_id, "Task added", f["title"], organization_id=oid)
    return redirect(url_for("cases.detail", case_id=case_id))

@bp.route("/<int:case_id>/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_task(case_id, task_id):
    with db_conn() as conn:
        case = _case_in_user_org(conn, case_id, g.user)
        if not case:
            abort(404)
        assigned_ids = [a["user_id"] for a in conn.execute(
            "SELECT user_id FROM case_assignments WHERE case_id=?", (case_id,)).fetchall()]
    can_edit = g.user["role"] in ("admin", "owner", "super_admin") or (g.user["role"] == "staff" and g.user["id"] in assigned_ids)
    if not can_edit:
        abort(403)

    with db_conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=? AND case_id=?", (task_id, case_id)).fetchone()
        if task:
            new_val = 0 if task["is_completed"] else 1
            if new_val:
                conn.execute("""
                    UPDATE tasks SET is_completed=?, completed_at=datetime('now')
                    WHERE id=?
                """, (new_val, task_id))
            else:
                conn.execute("""
                    UPDATE tasks SET is_completed=?, completed_at=NULL
                    WHERE id=?
                """, (new_val, task_id))
    return redirect(url_for("cases.detail", case_id=case_id))
