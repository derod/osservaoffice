#!/usr/bin/env python3
"""Seed OSSERVA OFFICE with demo data."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_db, db_conn
from app.auth_utils import hash_password
from datetime import datetime, timedelta

def seed():
    init_db()
    print("🌱 Seeding database...")

    with db_conn() as conn:
        # Clear all data
        for t in ["activity_logs","documents","schedule_requests","tasks",
                  "appointments","case_assignments","cases","clients","users"]:
            conn.execute(f"DELETE FROM {t}")

    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    with db_conn() as conn:
        # ── USERS ──
        users_data = [
            ("Marco Rossi",   "marco@osservaoffice.com",  "owner", "Managing Partner",  "#6366f1"),
            ("Elena Bianchi", "elena@osservaoffice.com",  "admin", "Office Manager",    "#14b8a6"),
            ("Luca Moretti",  "luca@osservaoffice.com",   "staff", "Senior Associate",  "#8b5cf6"),
            ("Sofia Conti",   "sofia@osservaoffice.com",  "staff", "Junior Associate",  "#ec4899"),
            ("Andrea Ferrari","andrea@osservaoffice.com", "staff", "Paralegal",         "#f59e0b"),
            ("Giulia Romano", "giulia@osservaoffice.com", "staff", "Legal Assistant",   "#10b981"),
            ("Paolo Marino",  "paolo@osservaoffice.com",  "staff", "Associate",         "#3b82f6"),
        ]
        user_ids = {}
        for name, email, role, title, color in users_data:
            cur = conn.execute("""
                INSERT INTO users (full_name, email, hashed_password, role, job_title, avatar_color, is_active)
                VALUES (?,?,?,?,?,?,?)
            """, (name, email, hash_password("password123"), role, title, color, 1 if name != "Paolo Marino" else 0))
            user_ids[email] = cur.lastrowid

        marco  = user_ids["marco@osservaoffice.com"]
        elena  = user_ids["elena@osservaoffice.com"]
        luca   = user_ids["luca@osservaoffice.com"]
        sofia  = user_ids["sofia@osservaoffice.com"]
        andrea = user_ids["andrea@osservaoffice.com"]
        giulia = user_ids["giulia@osservaoffice.com"]

        # ── CLIENTS ──
        clients_data = [
            ("Maria Lombardi",     None,              "maria.l@email.com",  "+39 06 987 6543"),
            ("Fiat Industries S.p.A.", "Fiat Industries", "legal@fiat.com", "+39 011 123 4567"),
            ("Giovanni Russo",     None,              "g.russo@email.com",  "+39 055 444 3322"),
            ("TechStart S.r.l.",   "TechStart",       "info@techstart.it",  "+39 02 555 0101"),
            ("EcoGreen Corp",      "EcoGreen",        "legal@ecogreen.eu",  "+39 02 888 9900"),
        ]
        cids = {}
        for name, company, email, phone in clients_data:
            cur = conn.execute(
                "INSERT INTO clients (full_name, company_name, email, phone) VALUES (?,?,?,?)",
                (name, company, email, phone)
            )
            cids[name] = cur.lastrowid

        # ── CASES ──
        cases = [
            dict(title="Lombardi Estate Planning",
                 desc="Comprehensive estate plan including wills, trusts, and power of attorney.",
                 status="open", priority="medium", client="Maria Lombardi",
                 due=today+timedelta(days=60),
                 overview="Estate planning for Maria Lombardi.",
                 current_step="Drafting will and trust documents.",
                 next_action="Send first draft to client for review.",
                 blockers=None, assignees=[sofia]),
            dict(title="Fiat Trademark Dispute",
                 desc="Trademark infringement case involving unauthorized use of the Fiat brand logo.",
                 status="in_progress", priority="high", client="Fiat Industries S.p.A.",
                 due=today+timedelta(days=13),
                 overview="Trademark infringement by third party manufacturer.",
                 current_step="Preparing motion for preliminary injunction.",
                 next_action="File motion for preliminary injunction by Feb 28.",
                 blockers="Awaiting notarized exhibits from client.", assignees=[luca, andrea]),
            dict(title="Russo Divorce Proceedings",
                 desc="Uncontested divorce with asset division and custody arrangement.",
                 status="waiting", priority="low", client="Giovanni Russo",
                 due=today+timedelta(days=79),
                 overview="Uncontested divorce proceedings.",
                 current_step="Waiting for opposing counsel response.",
                 next_action="Follow up with opposing counsel.",
                 blockers="Opposing party has not responded.", assignees=[sofia]),
            dict(title="Lombardi Property Sale",
                 desc="Sale of residential property in Rome. Completed successfully.",
                 status="closed", priority="low", client="Maria Lombardi",
                 due=today-timedelta(days=32),
                 overview="Property sale transaction.", current_step="Completed.",
                 next_action=None, blockers=None, assignees=[giulia]),
            dict(title="TechStart Series A Funding",
                 desc="Legal review and documentation for Series A funding round of €5M.",
                 status="in_progress", priority="high", client="TechStart S.r.l.",
                 due=today+timedelta(days=11),
                 overview="Series A round documentation.",
                 current_step="Reviewing shareholder agreements.",
                 next_action="Finalize shareholder agreement draft.",
                 blockers=None, assignees=[luca, sofia, giulia]),
            dict(title="EcoGreen Regulatory Compliance",
                 desc="EU environmental regulation compliance audit and remediation plan.",
                 status="open", priority="medium", client="EcoGreen Corp",
                 due=today+timedelta(days=134),
                 overview="Full EU regulatory compliance review.",
                 current_step="Conducting initial audit.",
                 next_action="Schedule site visit for audit.",
                 blockers=None, assignees=[luca, andrea]),
        ]
        case_ids = {}
        for c in cases:
            due_str = c["due"].strftime("%Y-%m-%d %H:%M:%S") if c["due"] else None
            closed = today.strftime("%Y-%m-%d %H:%M:%S") if c["status"] == "closed" else None
            cur = conn.execute("""
                INSERT INTO cases (title, description, status, priority, client_id,
                    due_date, overview, current_step, next_action, blockers, closed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (c["title"], c["desc"], c["status"], c["priority"],
                  cids.get(c["client"]), due_str,
                  c["overview"], c["current_step"], c.get("next_action"),
                  c.get("blockers"), closed))
            cid = cur.lastrowid
            case_ids[c["title"]] = cid
            for uid in c["assignees"]:
                conn.execute("INSERT OR IGNORE INTO case_assignments (case_id, user_id) VALUES (?,?)",
                    (cid, uid))

        # ── APPOINTMENTS (today) ──
        def appt(title, h_start, m_start, h_end, m_end, uid, atype="appointment", case_k=None, client_k=None):
            s = today.replace(hour=h_start, minute=m_start)
            e = today.replace(hour=h_end, minute=m_end)
            conn.execute("""
                INSERT INTO appointments (title, start_datetime, end_datetime,
                    assigned_to_user_id, appointment_type, case_id, client_id, created_by_user_id)
                VALUES (?,?,?,?,?,?,?,?)
            """, (title, s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S"),
                  uid, atype,
                  case_ids.get(case_k), cids.get(client_k), elena))

        appt("Team Standup",          9,  0,  9, 30, elena, "meeting")
        appt("Internal Training",    16,  0, 17, 30, elena, "meeting")
        appt("Fiat Case Review",     10,  0, 11, 30, luca,  "meeting",      "Fiat Trademark Dispute",    "Fiat Industries S.p.A.")
        appt("Client Meeting — TechStart", 14, 0, 15, 0, luca, "appointment", "TechStart Series A Funding", "TechStart S.r.l.")
        appt("Draft Estate Plan",    10,  0, 12,  0, sofia, "task",         "Lombardi Estate Planning",  "Maria Lombardi")
        appt("Lunch Meeting — Lombardi", 12, 30, 13, 30, sofia, "meeting",  None,                        "Maria Lombardi")
        appt("Compliance Research",  13,  0, 15,  0, andrea,"task",         "EcoGreen Regulatory Compliance")
        appt("Document Filing",      11,  0, 12,  0, giulia,"task")

        # ── TASKS ──
        def task(title, case_k, uid, days, priority="medium"):
            due = (today + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO tasks (title, case_id, assigned_to_user_id, due_date, priority, created_by_user_id)
                VALUES (?,?,?,?,?,?)
            """, (title, case_ids.get(case_k), uid, due, priority, elena))

        task("Review Lombardi Will Draft",     "Lombardi Estate Planning",       sofia,  3)
        task("Prepare Injunction Motion",      "Fiat Trademark Dispute",         luca,   0, "high")
        task("Contact Opposing Counsel",       "Russo Divorce Proceedings",      sofia,  1)
        task("Finalize Shareholder Agreement", "TechStart Series A Funding",     luca,   0, "high")
        task("Schedule EcoGreen Site Visit",   "EcoGreen Regulatory Compliance", andrea, 7)

        # ── SCHEDULE REQUESTS ──
        conn.execute("""
            INSERT INTO schedule_requests
                (requested_employee_id, created_by_user_id, request_type,
                 requested_start_datetime, requested_end_datetime, reason, priority, status)
            VALUES (?,?,?,?,?,?,?,?)
        """, (luca, elena, "new_meeting",
              (today+timedelta(days=2, hours=10)).strftime("%Y-%m-%d %H:%M:%S"),
              (today+timedelta(days=2, hours=11)).strftime("%Y-%m-%d %H:%M:%S"),
              "Client meeting for Fiat case", "high", "pending"))
        conn.execute("""
            INSERT INTO schedule_requests
                (requested_employee_id, created_by_user_id, request_type,
                 requested_start_datetime, requested_end_datetime, reason, priority, status)
            VALUES (?,?,?,?,?,?,?,?)
        """, (sofia, marco, "time_off",
              (today+timedelta(days=5, hours=9)).strftime("%Y-%m-%d %H:%M:%S"),
              (today+timedelta(days=5, hours=18)).strftime("%Y-%m-%d %H:%M:%S"),
              "Personal day request", "low", "pending"))

        # Activity logs
        for case_k in ["Fiat Trademark Dispute", "TechStart Series A Funding", "Lombardi Estate Planning"]:
            conn.execute("INSERT INTO activity_logs (user_id, case_id, action) VALUES (?,?,?)",
                (elena, case_ids[case_k], "Case created"))

    print("✅ Seed complete!")
    print("\n📋 Login credentials:")
    print("  Owner : marco@osservaoffice.com  / password123")
    print("  Admin : elena@osservaoffice.com  / password123")
    print("  Staff : luca@osservaoffice.com   / password123")
    print("  Staff : sofia@osservaoffice.com  / password123")
    print("\n🚀 Run: python run.py")

if __name__ == "__main__":
    seed()
