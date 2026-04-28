from flask import Blueprint, render_template, request, redirect, url_for, g, abort, flash
from app.auth_utils import login_required, is_admin_like, org_filter, org_id_for
from app.database import db_conn
from datetime import datetime, timedelta

bp = Blueprint("employees", __name__, url_prefix="/employees")

def get_emp_status(user_id, conn):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    active = conn.execute(
        "SELECT id FROM appointments WHERE assigned_to_user_id=? AND start_datetime<=? AND end_datetime>=? LIMIT 1",
        (user_id, now, now)
    ).fetchone()
    if active:
        return "in_meeting"
    today_end = datetime.utcnow().replace(hour=23, minute=59).strftime("%Y-%m-%d %H:%M:%S")
    upcoming = conn.execute(
        "SELECT id FROM appointments WHERE assigned_to_user_id=? AND start_datetime>=? AND start_datetime<=? LIMIT 1",
        (user_id, now, today_end)
    ).fetchone()
    return "busy" if upcoming else "free"

@bp.route("")
@login_required
def list_employees():
    role_filter = request.args.get("role", "all")
    status_filter = request.args.get("status", "all")
    today = datetime.utcnow().replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    today_end = datetime.utcnow().replace(hour=23, minute=59).strftime("%Y-%m-%d %H:%M:%S")

    current_role = g.user["role"]
    uc, up = org_filter(g.user)
    with db_conn() as conn:
        q = f"SELECT * FROM users WHERE 1=1{uc}"
        params = list(up)

        # super_admin is always excluded from tenant-level directory listings.
        # This catches any legacy records that may have organization_id set.
        q += " AND role != 'super_admin'"

        # Clamp the role_filter so URL params can never bypass visibility rules.
        # Staff see all non-super_admin members of their org (read-only directory).
        # super_admin filter is blocked for everyone at this level.
        if role_filter == "super_admin":
            role_filter = "all"
        if role_filter != "all":
            q += " AND role=?"; params.append(role_filter)

        if status_filter == "active":
            q += " AND is_active=1"
        elif status_filter == "inactive":
            q += " AND is_active=0"
        q += " ORDER BY full_name"
        users = [dict(r) for r in conn.execute(q, params).fetchall()]

        employee_data = []
        for emp in users:
            status = get_emp_status(emp["id"], conn)
            today_appts = conn.execute("""
                SELECT * FROM appointments
                WHERE assigned_to_user_id=? AND start_datetime>=? AND start_datetime<=?
                ORDER BY start_datetime
            """, (emp["id"], today, today_end)).fetchall()
            employee_data.append({
                "user": emp,
                "status": status,
                "today_appointments": [dict(a) for a in today_appts]
            })

    return render_template("employees/list.html",
        current_user=g.user,
        employee_data=employee_data,
        selected_role=role_filter,
        selected_status=status_filter,
        now=datetime.utcnow(),
        is_admin=is_admin_like(g.user),
    )

@bp.route("/<int:user_id>/agenda")
@login_required
def agenda(user_id):
    current_role = g.user["role"]

    # Staff can only view their own agenda
    if current_role == "staff" and g.user["id"] != user_id:
        return redirect(url_for("employees.agenda", user_id=g.user["id"]))

    view = request.args.get("view", "day")
    date_str = request.args.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    except:
        target = datetime.utcnow().replace(hour=0, minute=0, second=0)

    if view == "week":
        start = target - timedelta(days=target.weekday())
        end = start + timedelta(days=7)
        week_days = [start + timedelta(days=i) for i in range(7)]
    else:
        start = target.replace(hour=0, minute=0, second=0)
        end = target.replace(hour=23, minute=59, second=59)
        week_days = []

    now_dt = datetime.utcnow()
    seven_days = now_dt + timedelta(days=7)

    with db_conn() as conn:
        employee = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not employee:
            abort(404)
        employee = dict(employee)

        # Prevent non-super-admin from viewing agenda of users outside their org
        if current_role != "super_admin":
            if employee.get("organization_id") != g.user.get("organization_id"):
                abort(403)

        # Prevent admin/owner from viewing super_admin agenda
        if employee["role"] == "super_admin" and current_role != "super_admin":
            abort(403)
        appointments = [dict(r) for r in conn.execute("""
            SELECT * FROM appointments
            WHERE assigned_to_user_id=? AND start_datetime>=? AND start_datetime<=?
            ORDER BY start_datetime
        """, (user_id, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))).fetchall()]
        emp_status = get_emp_status(user_id, conn)

        # Priority cases: assigned to this employee, not closed
        priority_cases = [dict(r) for r in conn.execute("""
            SELECT c.id, c.title, c.status, c.priority, c.due_date, c.next_action
            FROM cases c
            JOIN case_assignments ca ON ca.case_id = c.id
            WHERE ca.user_id = ? AND c.status != 'closed'
            ORDER BY
                CASE c.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                c.due_date ASC NULLS LAST
        """, (user_id,)).fetchall()]

        # Upcoming appointments for the next 7 days
        upcoming_appts = [dict(r) for r in conn.execute("""
            SELECT title, start_datetime, end_datetime
            FROM appointments
            WHERE assigned_to_user_id = ?
              AND start_datetime >= ?
              AND start_datetime <= ?
            ORDER BY start_datetime
        """, (user_id,
              now_dt.strftime("%Y-%m-%d %H:%M:%S"),
              seven_days.strftime("%Y-%m-%d %H:%M:%S"))).fetchall()]

        # Pending schedule requests submitted by this employee
        pending_requests = [dict(r) for r in conn.execute("""
            SELECT request_type, requested_start_datetime, requested_end_datetime, status, reason
            FROM schedule_requests
            WHERE requested_employee_id = ? AND status = 'pending'
            ORDER BY requested_start_datetime
        """, (user_id,)).fetchall()]

        # Recent check-ins — filterable by range, status, and case
        ci_range = request.args.get("ci_range", "14d")
        ci_status = request.args.get("ci_status", "all")
        ci_case = request.args.get("ci_case", "all")

        range_map = {
            "today": 0, "week": None, "7d": 7, "14d": 14, "30d": 30,
        }
        if ci_range == "today":
            ci_from = now_dt.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        elif ci_range == "week":
            ci_from = (now_dt - timedelta(days=now_dt.weekday())).replace(
                hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        else:
            days_back = range_map.get(ci_range, 14)
            ci_from = (now_dt - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M:%S")

        ci_sql = """
            SELECT ci.id, ci.checked_in_at, ci.status, ci.notes, ci.case_id,
                   ci.source, c.title as case_title,
                   ci.checked_out_at, ci.checkout_status, ci.checkout_notes
            FROM checkins ci
            LEFT JOIN cases c ON c.id = ci.case_id
            WHERE ci.user_id = ? AND ci.checked_in_at >= ?
        """
        ci_params = [user_id, ci_from]

        if ci_status in ("on_time", "late", "exception"):
            ci_sql += " AND ci.status = ?"
            ci_params.append(ci_status)
        if ci_case != "all":
            try:
                case_id_int = int(ci_case)
                ci_sql += " AND ci.case_id = ?"
                ci_params.append(case_id_int)
            except (ValueError, TypeError):
                pass

        ci_sql += " ORDER BY ci.checked_in_at DESC"
        recent_checkins = [dict(r) for r in conn.execute(ci_sql, ci_params).fetchall()]

        # Today's check-in (if any)
        today_str = now_dt.strftime("%Y-%m-%d")
        todays_checkin = conn.execute("""
            SELECT ci.id, ci.checked_in_at, ci.status, ci.notes, ci.case_id,
                   c.title as case_title,
                   ci.checked_out_at, ci.checkout_status, ci.checkout_notes
            FROM checkins ci
            LEFT JOIN cases c ON c.id = ci.case_id
            WHERE ci.user_id = ? AND ci.checked_in_at >= ? AND ci.checked_in_at < ?
            ORDER BY ci.checked_in_at DESC LIMIT 1
        """, (user_id, today_str + " 00:00:00", today_str + " 23:59:59")).fetchone()
        todays_checkin = dict(todays_checkin) if todays_checkin else None

        # Cases assigned to this employee (for checkin case dropdown)
        assigned_cases = [dict(r) for r in conn.execute("""
            SELECT c.id, c.title FROM cases c
            JOIN case_assignments ca ON ca.case_id = c.id
            WHERE ca.user_id = ? AND c.status != 'closed'
            ORDER BY c.title
        """, (user_id,)).fetchall()]

        # Case Health — cases with open task counts and nearest task deadline
        now_str = now_dt.strftime("%Y-%m-%d")
        in48h = (now_dt + timedelta(hours=48)).strftime("%Y-%m-%d")
        case_health = [dict(r) for r in conn.execute("""
            SELECT c.id, c.title, c.status, c.priority, c.due_date,
                   c.next_action, c.court_name, c.case_number,
                   COUNT(t.id) AS open_tasks,
                   SUM(CASE WHEN t.due_date IS NOT NULL AND t.due_date < ? THEN 1 ELSE 0 END) AS overdue_tasks,
                   SUM(CASE WHEN t.due_date IS NOT NULL AND t.due_date >= ? AND t.due_date <= ? THEN 1 ELSE 0 END) AS urgent_tasks,
                   MIN(CASE WHEN t.due_date IS NOT NULL AND t.due_date >= ? THEN t.due_date END) AS next_task_deadline
            FROM cases c
            JOIN case_assignments ca ON ca.case_id = c.id
            LEFT JOIN tasks t ON t.case_id = c.id AND t.is_completed = 0
            WHERE ca.user_id = ? AND c.status != 'closed'
            GROUP BY c.id
            ORDER BY
                CASE c.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                c.due_date ASC NULLS LAST
        """, (now_str, now_str, in48h, now_str, user_id)).fetchall()]

        # Summary stats across all assigned cases
        total_open_tasks = sum(ch["open_tasks"] for ch in case_health)
        total_overdue_tasks = sum(ch["overdue_tasks"] for ch in case_health)
        total_urgent_tasks = sum(ch["urgent_tasks"] for ch in case_health)
        # Nearest case due date
        case_deadlines = [ch["due_date"] for ch in case_health if ch["due_date"]]
        next_case_deadline = min(case_deadlines) if case_deadlines else None
        # Nearest task deadline
        task_deadlines = [ch["next_task_deadline"] for ch in case_health if ch["next_task_deadline"]]
        next_task_deadline = min(task_deadlines) if task_deadlines else None

        health_summary = {
            "total_open_tasks": total_open_tasks,
            "total_overdue_tasks": total_overdue_tasks,
            "total_urgent_tasks": total_urgent_tasks,
            "next_case_deadline": next_case_deadline,
            "next_task_deadline": next_task_deadline,
        }

    return render_template("employees/agenda.html",
        current_user=g.user, employee=employee,
        appointments=appointments, view=view,
        target_date=target, hours=list(range(7,21)),
        week_days=week_days, emp_status=emp_status,
        priority_cases=priority_cases,
        upcoming_appts=upcoming_appts,
        pending_requests=pending_requests,
        recent_checkins=recent_checkins,
        todays_checkin=todays_checkin,
        assigned_cases=assigned_cases,
        now=now_dt,
        ci_range=ci_range,
        ci_status=ci_status,
        ci_case=ci_case,
        case_health=case_health,
        health_summary=health_summary,
    )


@bp.route("/<int:user_id>/checkin/<int:checkin_id>/delete", methods=["POST"])
@login_required
def delete_checkin(user_id, checkin_id):
    if not is_admin_like(g.user):
        abort(403)
    with db_conn() as conn:
        # Verify the checkin belongs to this employee and fetch details for audit
        ci = conn.execute(
            "SELECT id, checked_in_at, status, notes FROM checkins WHERE id=? AND user_id=?",
            (checkin_id, user_id)
        ).fetchone()
        if ci:
            ci = dict(ci)
            conn.execute("DELETE FROM checkins WHERE id=?", (checkin_id,))
            conn.execute("""
                INSERT INTO activity_logs (user_id, action, details, created_at, organization_id)
                VALUES (?, ?, ?, datetime('now'), ?)
            """, (g.user["id"], "checkin_deleted",
                  f"Deleted check-in #{checkin_id} for user {user_id}: "
                  f"status={ci['status']}, at={ci['checked_in_at']}, notes={ci.get('notes') or ''}",
                  org_id_for(g.user)))
            flash("Check-in entry deleted.", "success")
        else:
            flash("Check-in entry not found.", "error")
    return redirect(url_for("employees.agenda", user_id=user_id))


@bp.route("/<int:user_id>/checkout", methods=["POST"])
@login_required
def checkout(user_id):
    # Staff can only clock out for themselves
    if g.user["role"] == "staff" and g.user["id"] != user_id:
        abort(403)
    checkout_status = request.form.get("checkout_status", "finished")
    if checkout_status not in ("finished", "early", "exception"):
        checkout_status = "finished"
    checkout_notes = request.form.get("checkout_notes", "").strip() or None
    checked_out_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    source = "admin" if g.user["id"] != user_id else "self"

    with db_conn() as conn:
        # Find today's most recent open check-in (no checkout yet)
        open_checkin = conn.execute("""
            SELECT id FROM checkins
            WHERE user_id = ? AND checked_in_at >= ? AND checked_in_at < ?
              AND checked_out_at IS NULL
            ORDER BY checked_in_at DESC LIMIT 1
        """, (user_id, today_str + " 00:00:00", today_str + " 23:59:59")).fetchone()

        if not open_checkin:
            flash("No open check-in found for today. Please clock in first.", "error")
            return redirect(url_for("employees.agenda", user_id=user_id))

        conn.execute("""
            UPDATE checkins
            SET checked_out_at = ?, checkout_status = ?, checkout_notes = ?
            WHERE id = ?
        """, (checked_out_at, checkout_status, checkout_notes, open_checkin["id"]))

        action = "checkout_admin" if source == "admin" else "checkout_self"
        detail = (f"{'Admin' if source == 'admin' else 'Self'} clock-out for user {user_id}: "
                  f"status={checkout_status}, notes={checkout_notes or ''}")
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at, organization_id)
            VALUES (?, ?, ?, datetime('now'), ?)
        """, (g.user["id"], action, detail, org_id_for(g.user)))
        flash("Clock-out recorded.", "success")
    return redirect(url_for("employees.agenda", user_id=user_id))


@bp.route("/<int:user_id>/checkin", methods=["POST"])
@login_required
def checkin(user_id):
    # Staff can only check in for themselves
    if g.user["role"] == "staff" and g.user["id"] != user_id:
        abort(403)
    status = request.form.get("status", "on_time")
    if status not in ("on_time", "late", "exception"):
        status = "on_time"
    notes = request.form.get("notes", "").strip() or None
    case_id = request.form.get("case_id") or None
    if case_id:
        try:
            case_id = int(case_id)
        except (ValueError, TypeError):
            case_id = None
    checked_in_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    source = "admin" if g.user["id"] != user_id else "self"
    oid = org_id_for(g.user)
    with db_conn() as conn:
        conn.execute("""
            INSERT INTO checkins (user_id, checked_in_at, status, notes, case_id, source, organization_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, checked_in_at, status, notes, case_id, source, oid))
        # Audit log for every check-in
        action = "checkin_admin_created" if source == "admin" else "checkin_self"
        detail = (f"{'Admin' if source == 'admin' else 'Self'} check-in for user {user_id}: "
                  f"status={status}, notes={notes or ''}")
        conn.execute("""
            INSERT INTO activity_logs (user_id, action, details, created_at, organization_id)
            VALUES (?, ?, ?, datetime('now'), ?)
        """, (g.user["id"], action, detail, oid))
        flash("Check-in recorded.", "success")
    return redirect(url_for("employees.agenda", user_id=user_id))
