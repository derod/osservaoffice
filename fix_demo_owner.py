#!/usr/bin/env python3
"""Fix demo owner: find or create demo@osservaoffice.com in org 2."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn
from app.auth_utils import hash_password

with db_conn() as conn:
    # Check if user exists
    user = conn.execute(
        "SELECT id, email, role, organization_id, is_active FROM users WHERE email = ?",
        ("demo@osservaoffice.com",),
    ).fetchone()

    if user:
        print(f"Found existing user: {dict(user)}")
        conn.execute(
            "UPDATE users SET organization_id = 2, role = 'owner', "
            "hashed_password = ?, is_active = 1, full_name = 'Marco Rossi', "
            "job_title = 'Managing Partner', avatar_color = '#6366f1', language = 'en' "
            "WHERE email = ?",
            (hash_password("demo"), "demo@osservaoffice.com"),
        )
        print("Updated: org=2, role=owner, password=demo")
    else:
        print("User NOT found — creating from scratch...")
        cur = conn.execute(
            "INSERT INTO users (full_name, email, hashed_password, role, job_title, "
            "avatar_color, is_active, language, organization_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Marco Rossi", "demo@osservaoffice.com", hash_password("demo"),
             "owner", "Managing Partner", "#6366f1", 1, "en", 2),
        )
        print(f"Created user id={cur.lastrowid}")

    # Verify
    verify = conn.execute(
        "SELECT id, email, role, organization_id, is_active FROM users WHERE email = ?",
        ("demo@osservaoffice.com",),
    ).fetchone()
    print(f"\nVerification: {dict(verify)}")
    print("\nLogin: demo@osservaoffice.com / demo")
