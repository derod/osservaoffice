#!/usr/bin/env python3
"""
demo_seed.py — One-time demo data loader for OSSERVA OFFICE.

Run manually only:
    python demo_seed.py

SAFETY GUARANTEES
-----------------
* Never deletes, modifies, or touches any existing organization, user, case,
  client, or setting that is not part of this demo dataset.
* Never touches super_admin records.
* Fully idempotent: running it twice produces the same state, not duplicates.
* All demo data lives inside a single isolated organization
  ("Studio Legale Rossi & Partners").
* Not called from seed.py, __init__.py, or any startup/deploy hook.
"""

import os
import sys
import random
from datetime import datetime, timedelta

# Allow running from the project root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn, init_db
from app.auth_utils import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")

def _table_has_column(conn, table: str, column: str) -> bool:
    """Works for both SQLite and PostgreSQL."""
    try:
        # PostgreSQL
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            (table, column),
        ).fetchone()
        if row is not None:
            return True
        # If the above returned nothing on SQLite it also means no; fall through
        return False
    except Exception:
        return False

def _table_exists(conn, table: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        return True
    except Exception:
        return False

def _get_or_create(conn, table: str, match: dict, insert: dict) -> tuple[int, bool]:
    """
    Return (id, created).
    Looks up a row by `match` fields; if not found, inserts `match | insert`.
    Never raises on duplicate.
    """
    where = " AND ".join(f"{k} = ?" for k in match)
    row = conn.execute(f"SELECT id FROM {table} WHERE {where}", list(match.values())).fetchone()
    if row:
        return row["id"], False
    data = {**match, **insert}
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values()),
    )
    return cur.lastrowid, True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_demo():
    print()
    print("=" * 60)
    print("  OSSERVA OFFICE — Demo Data Seeder")
    print("=" * 60)
    print()
    print("  ⚠  SECURITY WARNING")
    print("  Demo account created with password 'demo'.")
    print("  Change this password if the site is publicly accessible.")
    print()

    # Ensure schema exists (safe — uses CREATE TABLE IF NOT EXISTS)
    init_db()

    counters = {
        "team_created": 0,
        "clients_created": 0,
        "cases_created": 0,
        "announcements_created": 0,
        "appointments_created": 0,
    }

    today = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)

    with db_conn() as conn:

        # ── 1. ORGANIZATION ──────────────────────────────────────────────────
        org_id, org_created = _get_or_create(
            conn, "organizations",
            match={"name": "Studio Legale Rossi & Partners"},
            insert={"slug": "studio-legale-rossi", "plan": "trial",
                    "status": "active", "is_active": 1},
        )
        org_status = "created" if org_created else "reused"
        print(f"  Organization : {org_status}  (id={org_id})")

        # ── 2. DEMO OWNER ────────────────────────────────────────────────────
        owner_id, owner_created = _get_or_create(
            conn, "users",
            match={"email": "demo@osservaoffice.com"},
            insert={
                "full_name":        "Marco Rossi",
                "hashed_password":  hash_password("demo"),
                "role":             "owner",
                "job_title":        "Managing Partner",
                "avatar_color":     "#6366f1",
                "is_active":        1,
                "language":         "en",
                "organization_id":  org_id,
            },
        )
        owner_status = "created" if owner_created else "reused"
        print(f"  Demo owner   : {owner_status}  (demo@osservaoffice.com / demo)")

        # ── 3. TEAM MEMBERS ──────────────────────────────────────────────────
        # (email, full_name, role, job_title, color)
        TEAM = [
            ("giulia.bianchi@demo.osserva",   "Giulia Bianchi",   "admin", "Office Manager",      "#14b8a6"),
            ("alessandro.conti@demo.osserva",  "Alessandro Conti", "admin", "Senior Partner",      "#8b5cf6"),
            ("luca.ferrari@demo.osserva",      "Luca Ferrari",     "staff", "Senior Associate",    "#3b82f6"),
            ("sofia.romano@demo.osserva",      "Sofia Romano",     "staff", "Junior Associate",    "#ec4899"),
            ("matteo.ricci@demo.osserva",      "Matteo Ricci",     "staff", "Associate",           "#f59e0b"),
            ("chiara.gallo@demo.osserva",      "Chiara Gallo",     "staff", "Legal Assistant",     "#10b981"),
            ("davide.moretti@demo.osserva",    "Davide Moretti",   "staff", "Paralegal",           "#64748b"),
            ("elena.barbieri@demo.osserva",    "Elena Barbieri",   "staff", "Legal Secretary",     "#a855f7"),
        ]
        user_ids = {"demo@osservaoffice.com": owner_id}
        for email, name, role, title, color in TEAM:
            uid, created = _get_or_create(
                conn, "users",
                match={"email": email},
                insert={
                    "full_name":        name,
                    "hashed_password":  hash_password("demo123"),
                    "role":             role,
                    "job_title":        title,
                    "avatar_color":     color,
                    "is_active":        1,
                    "language":         "it",
                    "organization_id":  org_id,
                },
            )
            user_ids[email] = uid
            if created:
                counters["team_created"] += 1

        print(f"  Team members : {counters['team_created']} created  "
              f"({len(TEAM) - counters['team_created']} already existed)")

        # Shorthand references
        giulia    = user_ids["giulia.bianchi@demo.osserva"]
        luca      = user_ids["luca.ferrari@demo.osserva"]
        sofia     = user_ids["sofia.romano@demo.osserva"]
        matteo    = user_ids["matteo.ricci@demo.osserva"]
        chiara    = user_ids["chiara.gallo@demo.osserva"]
        davide    = user_ids["davide.moretti@demo.osserva"]

        # ── 4. CLIENTS ───────────────────────────────────────────────────────
        # (full_name, company_name, email, phone)
        CLIENTS = [
            # People
            ("Giovanni Esposito",   None,                        "g.esposito@email.it",      "+39 081 123 4567"),
            ("Francesca Lombardi",  None,                        "f.lombardi@email.it",      "+39 02 987 6543"),
            ("Antonio De Luca",     None,                        "a.deluca@email.it",        "+39 055 321 8877"),
            ("Paola Marino",        None,                        "p.marino@email.it",        "+39 06 654 3210"),
            ("Roberto Santoro",     None,                        "r.santoro@email.it",       "+39 011 789 0123"),
            ("Valentina Rinaldi",   None,                        "v.rinaldi@email.it",       "+39 049 456 7890"),
            ("Stefano Greco",       None,                        "s.greco@email.it",         "+39 091 234 5678"),
            # Companies
            ("ItalBuild S.r.l.",    "ItalBuild S.r.l.",          "legal@italbuild.it",       "+39 02 111 2233"),
            ("Milano Consulting Group", "Milano Consulting Group","info@milanoconsulting.it", "+39 02 444 5566"),
            ("Toscana Holding",     "Toscana Holding",           "legal@toscanaholding.it",  "+39 055 888 9900"),
            ("Roma Infrastrutture SPA", "Roma Infrastrutture SPA","info@romainfra.it",       "+39 06 333 4455"),
        ]
        client_ids = {}
        for full_name, company, email, phone in CLIENTS:
            cid, created = _get_or_create(
                conn, "clients",
                match={"full_name": full_name, "organization_id": org_id},
                insert={
                    "company_name":   company,
                    "email":          email,
                    "phone":          phone,
                    "is_active":      1,
                    "organization_id": org_id,
                },
            )
            client_ids[full_name] = cid
            if created:
                counters["clients_created"] += 1

        print(f"  Clients      : {counters['clients_created']} created  "
              f"({len(CLIENTS) - counters['clients_created']} already existed)")

        # ── 5. CASES ─────────────────────────────────────────────────────────
        CASES = [
            dict(
                title="Corporate restructuring — ItalBuild S.r.l.",
                description="Full corporate restructuring advisory including shareholder "
                            "agreement revision and governance reform.",
                status="in_progress", priority="high",
                client="ItalBuild S.r.l.",
                due=today + timedelta(days=21),
                overview="Advising ItalBuild on a complete corporate restructuring.",
                current_step="Reviewing current shareholder agreements.",
                next_action="Prepare restructuring proposal document.",
                assignees_keys=["luca.ferrari@demo.osserva", "giulia.bianchi@demo.osserva"],
            ),
            dict(
                title="Labor dispute — Giovanni Esposito",
                description="Wrongful termination claim filed against former employer. "
                            "Seeking reinstatement and back pay.",
                status="open", priority="high",
                client="Giovanni Esposito",
                due=today + timedelta(days=14),
                overview="Wrongful termination claim before the Labour Tribunal.",
                current_step="Filing initial claim documentation.",
                next_action="Submit claim to Tribunale del Lavoro.",
                assignees_keys=["sofia.romano@demo.osserva"],
            ),
            dict(
                title="Real estate acquisition — Milano Consulting Group",
                description="Due diligence and contract drafting for commercial "
                            "property acquisition in central Milan.",
                status="in_progress", priority="medium",
                client="Milano Consulting Group",
                due=today + timedelta(days=35),
                overview="Commercial property acquisition — Via Montenapoleone area.",
                current_step="Conducting title search and due diligence.",
                next_action="Deliver due diligence report to client.",
                assignees_keys=["chiara.gallo@demo.osserva", "luca.ferrari@demo.osserva"],
            ),
            dict(
                title="Contract litigation — Toscana Holding",
                description="Breach of contract dispute. Claimant seeking €850,000 "
                            "in damages for non-performance of supply agreement.",
                status="in_progress", priority="high",
                client="Toscana Holding",
                due=today + timedelta(days=10),
                overview="Breach of contract litigation before Tribunale di Firenze.",
                current_step="Preparing counter-claim brief.",
                next_action="File counter-claim by end of week.",
                blockers="Waiting for sworn translation of two exhibits.",
                assignees_keys=["luca.ferrari@demo.osserva", "davide.moretti@demo.osserva"],
            ),
            dict(
                title="Employment advisory — Paola Marino",
                description="Ongoing employment law advisory: redundancy procedure "
                            "compliance and severance negotiations.",
                status="open", priority="medium",
                client="Paola Marino",
                due=today + timedelta(days=45),
                overview="Employment advisory for redundancy and severance.",
                current_step="Reviewing employment contract and CCNL provisions.",
                next_action="Deliver written opinion on severance entitlement.",
                assignees_keys=["sofia.romano@demo.osserva"],
            ),
            dict(
                title="Commercial agreement drafting — Roma Infrastrutture SPA",
                description="Drafting and negotiating a multi-year infrastructure "
                            "services contract with a public-sector counterparty.",
                status="open", priority="medium",
                client="Roma Infrastrutture SPA",
                due=today + timedelta(days=28),
                overview="Long-form services contract drafting.",
                current_step="Initial draft under review by both parties.",
                next_action="Incorporate client comments into v2 draft.",
                assignees_keys=["chiara.gallo@demo.osserva", "giulia.bianchi@demo.osserva"],
            ),
            dict(
                title="M&A due diligence — Roberto Santoro",
                description="Buy-side legal due diligence for acquisition of a mid-size "
                            "logistics company. Target valuation: €12M.",
                status="in_progress", priority="high",
                client="Roberto Santoro",
                due=today + timedelta(days=18),
                overview="Buy-side due diligence for logistics company acquisition.",
                current_step="Legal DD report — 60% complete.",
                next_action="Complete IP and employment chapter of DD report.",
                blockers="Vendor data room access was granted late.",
                assignees_keys=["luca.ferrari@demo.osserva", "sofia.romano@demo.osserva",
                                "davide.moretti@demo.osserva"],
            ),
        ]
        case_ids = {}
        for c in CASES:
            cid, created = _get_or_create(
                conn, "cases",
                match={"title": c["title"], "organization_id": org_id},
                insert={
                    "description":   c["description"],
                    "status":        c["status"],
                    "priority":      c["priority"],
                    "client_id":     client_ids.get(c["client"]),
                    "due_date":      _dt(c["due"]),
                    "overview":      c.get("overview"),
                    "current_step":  c.get("current_step"),
                    "next_action":   c.get("next_action"),
                    "blockers":      c.get("blockers"),
                    "organization_id": org_id,
                },
            )
            case_ids[c["title"]] = cid
            if created:
                counters["cases_created"] += 1
                # Assign team members
                for email_key in c.get("assignees_keys", []):
                    uid = user_ids.get(email_key)
                    if uid:
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO case_assignments "
                                "(case_id, user_id) VALUES (?, ?)",
                                (cid, uid),
                            )
                        except Exception:
                            pass

        print(f"  Cases        : {counters['cases_created']} created  "
              f"({len(CASES) - counters['cases_created']} already existed)")

        # ── 6. ANNOUNCEMENTS ─────────────────────────────────────────────────
        ANNOUNCEMENTS = [
            ("Office closed Friday afternoon",
             "The office will close at 13:00 this Friday for a team event. "
             "All urgent matters should be handled before noon.",
             1),   # is_pinned
            ("New compliance policy update",
             "Please review the updated AML compliance procedures attached to this notice. "
             "All staff must confirm acknowledgement by end of month.",
             1),
            ("Billing cycle reminder",
             "Time entries for the current billing period are due by the 25th. "
             "Please ensure all client matters are up to date.",
             0),
            ("Team meeting Monday",
             "Mandatory all-hands meeting on Monday at 9:30 in the main conference room. "
             "Agenda will be circulated on Friday.",
             0),
            ("Court schedule adjustment",
             "The hearing in the Toscana Holding matter has been rescheduled to the 18th. "
             "The case team has been notified.",
             0),
        ]
        for title, content, pinned in ANNOUNCEMENTS:
            _, created = _get_or_create(
                conn, "announcements",
                match={"title": title, "organization_id": org_id},
                insert={
                    "content":         content,
                    "is_pinned":       pinned,
                    "user_id":         owner_id,
                    "organization_id": org_id,
                },
            )
            if created:
                counters["announcements_created"] += 1

        print(f"  Announcements: {counters['announcements_created']} created  "
              f"({len(ANNOUNCEMENTS) - counters['announcements_created']} already existed)")

        # ── 7. APPOINTMENTS (next 7 days) ────────────────────────────────────
        if _table_exists(conn, "appointments"):
            # Only insert if none already exist for this org in the next 7 days
            existing = conn.execute(
                "SELECT COUNT(*) FROM appointments WHERE organization_id = ?",
                (org_id,),
            ).fetchone()
            existing_count = existing[0] if existing else 0

            if existing_count == 0:
                APPTS = [
                    # (title, day_offset, h_start, m_start, h_end, m_end, user_key, atype, case_title, client_name)
                    ("Team standup",                    0, 9,  0,  9, 30, "giulia.bianchi@demo.osserva",  "meeting",      None,                                               None),
                    ("ItalBuild restructuring review",  0, 10, 0, 11, 30, "luca.ferrari@demo.osserva",    "meeting",      "Corporate restructuring — ItalBuild S.r.l.",        "ItalBuild S.r.l."),
                    ("Client call — Toscana Holding",   0, 14, 0, 14, 45, "luca.ferrari@demo.osserva",    "appointment",  "Contract litigation — Toscana Holding",             "Toscana Holding"),
                    ("DD report drafting — Santoro",    1, 9,  0, 12,  0, "luca.ferrari@demo.osserva",    "task",         "M&A due diligence — Roberto Santoro",               "Roberto Santoro"),
                    ("Employment advisory call",        1, 11, 0, 11, 45, "sofia.romano@demo.osserva",    "appointment",  "Employment advisory — Paola Marino",                "Paola Marino"),
                    ("Team standup",                    1, 9,  0,  9, 30, "giulia.bianchi@demo.osserva",  "meeting",      None,                                               None),
                    ("Milano real estate site visit",   2, 10, 0, 13,  0, "chiara.gallo@demo.osserva",    "appointment",  "Real estate acquisition — Milano Consulting Group", "Milano Consulting Group"),
                    ("Labor dispute filing deadline",   2, 14, 0, 15,  0, "sofia.romano@demo.osserva",    "task",         "Labor dispute — Giovanni Esposito",                 "Giovanni Esposito"),
                    ("Partner strategy meeting",        3, 9,  0, 10, 30, "demo@osservaoffice.com",       "meeting",      None,                                               None),
                    ("Contract review — Roma Infra",    3, 11, 0, 12, 30, "chiara.gallo@demo.osserva",    "task",         "Commercial agreement drafting — Roma Infrastrutture SPA", "Roma Infrastrutture SPA"),
                    ("Team standup",                    3, 9,  0,  9, 30, "giulia.bianchi@demo.osserva",  "meeting",      None,                                               None),
                    ("Due diligence presentation",      4, 14, 0, 15, 30, "luca.ferrari@demo.osserva",    "meeting",      "M&A due diligence — Roberto Santoro",               "Roberto Santoro"),
                    ("Court hearing prep",              5, 9,  0, 11,  0, "luca.ferrari@demo.osserva",    "task",         "Contract litigation — Toscana Holding",             "Toscana Holding"),
                    ("Client intake — Valentina Rinaldi", 5, 14, 0, 14, 45, "sofia.romano@demo.osserva", "appointment",  None,                                               "Valentina Rinaldi"),
                    ("Weekly billing review",           6, 10, 0, 11,  0, "giulia.bianchi@demo.osserva",  "meeting",      None,                                               None),
                    ("Team standup",                    6, 9,  0,  9, 30, "giulia.bianchi@demo.osserva",  "meeting",      None,                                               None),
                ]
                for (title, day_off, hs, ms, he, me, user_key,
                     atype, case_k, client_k) in APPTS:
                    day = today.replace(hour=0, minute=0) + timedelta(days=day_off)
                    start = day.replace(hour=hs, minute=ms)
                    end   = day.replace(hour=he, minute=me)
                    uid   = user_ids.get(user_key)
                    try:
                        conn.execute(
                            "INSERT INTO appointments "
                            "(title, start_datetime, end_datetime, assigned_to_user_id, "
                            "appointment_type, case_id, client_id, created_by_user_id, "
                            "organization_id) VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                title, _dt(start), _dt(end), uid, atype,
                                case_ids.get(case_k) if case_k else None,
                                client_ids.get(client_k) if client_k else None,
                                owner_id, org_id,
                            ),
                        )
                        counters["appointments_created"] += 1
                    except Exception as e:
                        print(f"  [warn] Appointment skipped ({title}): {e}")
            else:
                print(f"  [skip] Appointments: {existing_count} already exist for this org")

        print(f"  Appointments : {counters['appointments_created']} created")

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  DEMO SEED COMPLETE")
    print("=" * 60)
    print(f"  Organization      : {org_status}")
    print(f"  Demo owner        : {owner_status}  →  demo@osservaoffice.com")
    print(f"  Team members      : {counters['team_created']} created")
    print(f"  Clients           : {counters['clients_created']} created")
    print(f"  Cases / matters   : {counters['cases_created']} created")
    print(f"  Announcements     : {counters['announcements_created']} created")
    print(f"  Appointments      : {counters['appointments_created']} created")
    print()
    print("  Login at /auth/login with:")
    print("    Email    : demo@osservaoffice.com")
    print("    Password : demo")
    print()
    print("  ⚠  Change the demo password before exposing this to the public.")
    print()


if __name__ == "__main__":
    seed_demo()
