from flask import Blueprint, render_template, request, redirect, url_for, g, abort
from app.auth_utils import login_required, is_admin_like, org_filter, org_id_for
from app.database import db_conn
from datetime import datetime, timedelta

bp = Blueprint("calendar", __name__, url_prefix="/calendar")

@bp.route("")
@login_required
def index():
    view = request.args.get("view", "day")
    date_str = request.args.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    employee_id = request.args.get("employee_id", type=int)
    appt_type = request.args.get("appt_type", "")

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    except:
        target = datetime.utcnow().replace(hour=0, minute=0, second=0)

    if view == "week":
        start = target - timedelta(days=target.weekday())
        end = start + timedelta(days=7)
        week_days = [start + timedelta(days=i) for i in range(7)]
    elif view == "list":
        start = target
        end = target + timedelta(days=30)
        week_days = []
    else:
        start = target.replace(hour=0, minute=0, second=0)
        end = target.replace(hour=23, minute=59, second=59)
        week_days = []

    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end.strftime("%Y-%m-%d %H:%M:%S")

    oc, op = org_filter(g.user, alias="a")
    uc, up = org_filter(g.user)

    with db_conn() as conn:
        q = f"""
            SELECT a.*, u.full_name as assignee_name, u.avatar_color as assignee_color,
                   c.title as case_title, cl.full_name as client_name
            FROM appointments a
            LEFT JOIN users u ON u.id=a.assigned_to_user_id
            LEFT JOIN cases c ON c.id=a.case_id
            LEFT JOIN clients cl ON cl.id=a.client_id
            WHERE a.start_datetime>=? AND a.start_datetime<=?
            AND a.appointment_type != 'case_key_date'{oc}
        """
        params = [start_str, end_str] + op
        if g.user["role"] == "staff":
            q += " AND a.assigned_to_user_id=?"
            params.append(g.user["id"])
        elif employee_id:
            q += " AND a.assigned_to_user_id=?"
            params.append(employee_id)
        if appt_type:
            q += " AND a.appointment_type=?"
            params.append(appt_type)
        q += " ORDER BY a.start_datetime"

        appointments = [dict(r) for r in conn.execute(q, params).fetchall()]
        all_users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()]
        all_cases = [dict(r) for r in conn.execute(
            f"SELECT id, title FROM cases WHERE status!='closed'{uc} ORDER BY title", up
        ).fetchall()]
        all_clients = [dict(r) for r in conn.execute(
            f"SELECT id, full_name FROM clients WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()]

    hours = list(range(7, 21))
    if view == 'week':
        prev_date = target - timedelta(days=7)
        next_date = target + timedelta(days=7)
    elif view == 'list':
        prev_date = target - timedelta(days=30)
        next_date = target + timedelta(days=30)
    else:
        prev_date = target - timedelta(days=1)
        next_date = target + timedelta(days=1)
    return render_template("calendar/index.html",
        current_user=g.user,
        appointments=appointments,
        view=view, target_date=target,
        start_dt=start, end_dt=end,
        hours=hours, week_days=week_days,
        all_users=all_users, all_cases=all_cases, all_clients=all_clients,
        selected_employee=employee_id, selected_type=appt_type,
        now=datetime.utcnow(),
        prev_date=prev_date, next_date=next_date,
    )

@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_appointment():
    uc, up = org_filter(g.user)
    if request.method == "POST":
        f = request.form
        start_dt = f.get("start_date","") + " " + f.get("start_time","09:00") + ":00"
        end_dt = f.get("end_date","") + " " + f.get("end_time","10:00") + ":00"
        uid = f.get("assigned_to_user_id") or None
        if g.user["role"] == "staff":
            uid = g.user["id"]
        oid = org_id_for(g.user)
        with db_conn() as conn:
            conn.execute("""
                INSERT INTO appointments (title,description,start_datetime,end_datetime,
                    assigned_to_user_id,case_id,client_id,location,meeting_link,
                    appointment_type,created_by_user_id,organization_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (f["title"], f.get("description",""), start_dt, end_dt,
                  uid, f.get("case_id") or None, f.get("client_id") or None,
                  f.get("location",""), f.get("meeting_link",""),
                  f.get("appointment_type","appointment"), g.user["id"], oid))
        return redirect(url_for("calendar.index", date=f.get("start_date")))

    with db_conn() as conn:
        all_users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()]
        all_cases = [dict(r) for r in conn.execute(
            f"SELECT id, title FROM cases WHERE status!='closed'{uc}", up
        ).fetchall()]
        all_clients = [dict(r) for r in conn.execute(
            f"SELECT id, full_name FROM clients WHERE is_active=1{uc}", up
        ).fetchall()]

    return render_template("calendar/form.html",
        current_user=g.user, appointment=None,
        all_users=all_users, all_cases=all_cases, all_clients=all_clients,
    )

@bp.route("/<int:appt_id>/edit", methods=["GET","POST"])
@login_required
def edit_appointment(appt_id):
    oc, op = org_filter(g.user)
    uc, up = org_filter(g.user)
    with db_conn() as conn:
        appt = conn.execute(
            f"SELECT * FROM appointments WHERE id=?{oc}", [appt_id] + op
        ).fetchone()
        if not appt:
            return redirect(url_for("calendar.index"))
        appt = dict(appt)

        if request.method == "POST":
            f = request.form
            start_dt = f.get("start_date","") + " " + f.get("start_time","09:00") + ":00"
            end_dt = f.get("end_date","") + " " + f.get("end_time","10:00") + ":00"
            uid = f.get("assigned_to_user_id") or None
            if g.user["role"] == "staff":
                uid = appt["assigned_to_user_id"]
            conn.execute("""
                UPDATE appointments SET title=?,description=?,start_datetime=?,end_datetime=?,
                    assigned_to_user_id=?,case_id=?,client_id=?,location=?,meeting_link=?,
                    appointment_type=? WHERE id=?
            """, (f["title"], f.get("description",""), start_dt, end_dt,
                  uid, f.get("case_id") or None, f.get("client_id") or None,
                  f.get("location",""), f.get("meeting_link",""),
                  f.get("appointment_type","appointment"), appt_id))
            return redirect(url_for("calendar.index", date=f.get("start_date")))

        all_users = [dict(r) for r in conn.execute(
            f"SELECT * FROM users WHERE is_active=1{uc} ORDER BY full_name", up
        ).fetchall()]
        all_cases = [dict(r) for r in conn.execute(
            f"SELECT id, title FROM cases WHERE status!='closed'{uc}", up
        ).fetchall()]
        all_clients = [dict(r) for r in conn.execute(
            f"SELECT id, full_name FROM clients WHERE is_active=1{uc}", up
        ).fetchall()]

    return render_template("calendar/form.html",
        current_user=g.user, appointment=appt,
        all_users=all_users, all_cases=all_cases, all_clients=all_clients,
    )

@bp.route("/<int:appt_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appt_id):
    if is_admin_like(g.user):
        oc, op = org_filter(g.user)
        with db_conn() as conn:
            conn.execute(
                f"DELETE FROM appointments WHERE id=?{oc}", [appt_id] + op
            )
    return redirect(url_for("calendar.index"))
