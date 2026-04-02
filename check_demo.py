#!/usr/bin/env python3
"""Diagnostic: show demo org and user details."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn

with db_conn() as conn:
    print("\n--- Organizations ---")
    for r in conn.execute("SELECT id, name, slug, status FROM organizations ORDER BY id").fetchall():
        print(dict(r))

    print("\n--- Users (id, email, role, org_id) ---")
    for r in conn.execute("SELECT id, email, role, organization_id, is_active FROM users ORDER BY organization_id, role").fetchall():
        print(dict(r))
