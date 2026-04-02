#!/usr/bin/env python3
"""Debug: test the demo login exactly as the auth route does."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn
from app.auth_utils import hash_password, verify_password

with db_conn() as conn:
    user = conn.execute(
        "SELECT id, email, hashed_password, role, is_active, organization_id FROM users WHERE email = ?",
        ("demo@osservaoffice.com",),
    ).fetchone()

    if not user:
        print("ERROR: user not found")
        sys.exit(1)

    print(f"User found: id={user['id']}, role={user['role']}, org={user['organization_id']}, active={user['is_active']}")
    print(f"Hash stored: {user['hashed_password'][:50]}...")

    # Test verify exactly like the login route does
    result = verify_password("demo", user["hashed_password"])
    print(f"verify_password('demo', stored_hash) = {result}")

    if not result:
        print("\nPassword verification FAILED. Regenerating hash now...")
        new_hash = hash_password("demo")
        print(f"New hash: {new_hash[:50]}...")
        # Verify the new hash works
        print(f"verify_password('demo', new_hash) = {verify_password('demo', new_hash)}")
        # Update
        conn.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (new_hash, user["id"]))
        print("Updated in DB. Verifying again...")
        user2 = conn.execute("SELECT hashed_password FROM users WHERE id = ?", (user["id"],)).fetchone()
        print(f"Final verify: {verify_password('demo', user2['hashed_password'])}")
    else:
        print("\nPassword is CORRECT. Login should work.")
