#!/usr/bin/env python3
"""Fix demo owner: assign org_id=2 and reset password."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn
from app.auth_utils import hash_password

with db_conn() as conn:
    user = conn.execute("SELECT * FROM users WHERE email = ?", ("demo@osservaoffice.com",)).fetchone()
    if not user:
        print("ERROR: demo@osservaoffice.com not found in DB at all.")
    else:
        print(f"Found user: {dict(user)}")
        conn.execute(
            "UPDATE users SET organization_id = 2, role = 'owner', hashed_password = ?, is_active = 1 WHERE email = ?",
            (hash_password("demo"), "demo@osservaoffice.com"),
        )
        print("Fixed: organization_id=2, role=owner, password=demo, is_active=1")
