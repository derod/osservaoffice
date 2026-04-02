#!/usr/bin/env python3
"""One-off: reset the demo account password to 'demo'."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn
from app.auth_utils import hash_password

with db_conn() as conn:
    cur = conn.execute(
        "UPDATE users SET hashed_password = ? WHERE email = ?",
        (hash_password("demo"), "demo@osservaoffice.com"),
    )
    if cur.rowcount:
        print("Password reset to 'demo' for demo@osservaoffice.com")
    else:
        print("User not found: demo@osservaoffice.com")
