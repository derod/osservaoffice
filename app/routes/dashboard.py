from flask import Blueprint, render_template, g, redirect, url_for
from app.auth_utils import login_required, get_current_user, org_filter, org_id_for
from app.database import db_conn
from datetime import datetime, timedelta

bp = Blueprint("dashboard", __name__)

def get_employee_status(user_id, conn):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    active = conn.execute("""
        SELECT id FROM appointments
        WHERE assigned_to_user_id=? AND start_datetime<=? AND end_datetime>=?
        LIMIT 1
    """, (user_id, now, now)).fetchone()
    if active:
        return "in_meeting"
    today_end = (datetime.utcnow().replace(hour=23, minute=59)).strftime("%Y-%m-%d %H:%M:%S")
    upcoming = conn.execute("""
        SELECT id FROM appointments
        WHERE assigned_to_user_id=? AND start_datetime>=? AND start_datetime<=?
        LIMIT 1
    """, (user_id, now, today_end)).fetchone()
    return "busy" if upcoming else "free"

@bp.route("/")
def root():
    return redirect(url_for("dashboard.index"))

@bp.route("/dashboard")
@login_required
def index():
    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    next7 = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    next30 = (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    today_start = today_str + " 00:00:00"
    today_end = today_str + " 23:59:59"

    oc, op = org_filter(g.user)

    with db_conn() as conn:
        active_cases = conn.execute(
            f"SELECT COUNT(*) FROM cases WHERE status != 'closed'{oc}", op
        ).fetchone()[0]
        due_7 = conn.execute(
            f"SELECT COUNT(*) FROM cases WHERE status!='closed' AND due_date IS NOT NULL AND due_date<=? AND due_date>=?{oc}",
            [next7, now_str] + op
        ).fetchone()[0]
        due_30 = conn.execute(
            f"SELECT COUNT(*) FROM cases WHERE status!='closed' AND due_date IS NOT NULL AND due_date<=? AND due_date>=?{oc}",
            [next30, now_str] + op
        ).fetchone()[0]
        tasks_today = conn.execute(
            f"SELECT COUNT(*) FROM tasks WHERE is_completed=0 AND due_date>=? AND due_date<=?{oc}",
            [today_start, today_end] + op
        ).fetchone()[0]
        appts_today = conn.execute(
            f"SELECT COUNT(*) FROM appointments WHERE start_datetime>=? AND start_datetime<=?{oc}",
            [today_start, today_end] + op
        ).fetchone()[0]
        pending_requests = conn.execute(
            f"SELECT COUNT(*) FROM schedule_requests WHERE status='pending'{oc}", op
        ).fetchone()[0]
        docs_count = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE 1=1{oc}", op
        ).fetchone()[0]

        # Team — scoped to org (super_admin sees all except other super_admins)
        uc, up = org_filter(g.user)
        staff = conn.execute(
            f"SELECT * FROM users WHERE is_active=1 AND role NOT IN ('owner','super_admin'){uc} ORDER BY full_name",
            up
        ).fetchall()
        staff = [dict(s) for s in staff]

        # Pending requests for sidebar panel
        src, srp = org_filter(g.user, alias="sr")
        pending_reqs = conn.execute(
            f"""SELECT sr.*, u.full_name as emp_name, u.avatar_color as emp_color
            FROM schedule_requests sr
            LEFT JOIN users u ON u.id=sr.requested_employee_id
            WHERE sr.status='pending'{src}
            ORDER BY sr.created_at DESC LIMIT 5""",
            srp
        ).fetchall()
        pending_reqs = [dict(r) for r in pending_reqs]

        # Employee cards — batch all appointment lookups in one query to avoid N+1
        employee_cards = []
        if staff:
            staff_ids = [emp["id"] for emp in staff]
            placeholders = ",".join("?" * len(staff_ids))
            batch_appts = conn.execute(f"""
                SELECT * FROM appointments
                WHERE assigned_to_user_id IN ({placeholders})
                  AND end_datetime >= ?
                ORDER BY start_datetime
            """, staff_ids + [now_str]).fetchall()
            batch_appts = [dict(a) for a in batch_appts]

            appts_by_user: dict = {}
            for a in batch_appts:
                appts_by_user.setdefault(a["assigned_to_user_id"], []).append(a)

            today_end_check = today_str + " 23:59:59"
            for emp in staff:
                emp_appts = appts_by_user.get(emp["id"], [])
                status = "free"
                for a in emp_appts:
                    if a["start_datetime"] <= now_str and a["end_datetime"] >= now_str:
                        status = "in_meeting"
                        break
                if status == "free":
                    for a in emp_appts:
                        if now_str <= a["start_datetime"] <= today_end_check:
                            status = "busy"
                            break
                next_appt = next(
                    (a for a in emp_appts if a["start_datetime"] >= now_str), None
                )
                employee_cards.append({
                    "user": emp,
                    "status": status,
                    "next_appointment": next_appt,
                })

        free_count = sum(1 for e in employee_cards if e["status"] == "free")

    return render_template("dashboard/index.html",
        current_user=g.user,
        active_cases=active_cases,
        due_7_days=due_7,
        due_30_days=due_30,
        tasks_today=tasks_today,
        appointments_today=appts_today,
        pending_requests=pending_requests,
        recent_docs_count=docs_count,
        team_available=free_count,
        team_total=len(staff),
        employee_cards=employee_cards,
        pending_req_list=pending_reqs,
        now=now,
    )
