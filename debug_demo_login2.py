#!/usr/bin/env python3
"""Debug: simulate the exact login route flow."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn
from app.auth_utils import verify_password

email = "demo@osservaoffice.com"
password = "demo"

with db_conn() as conn:
    # Exact same query as auth.py line 34
    user = conn.execute(
        "SELECT * FROM users WHERE email=?", (email,)
    ).fetchone()

    if not user:
        print(f"NOT FOUND with email='{email}'")
        # Try LIKE search
        rows = conn.execute("SELECT id, email FROM users WHERE email LIKE ?", ("%demo%",)).fetchall()
        print(f"LIKE '%demo%' results: {[dict(r) for r in rows]}")
        sys.exit(1)

    print(f"Found: id={user['id']}, email='{user['email']}', active={user['is_active']}")
    print(f"Hash: {user['hashed_password']}")
    print(f"Hash length: {len(user['hashed_password'])}")
    print(f"Hash repr: {repr(user['hashed_password'][:80])}")

    # Check for is_active
    if not user["is_active"]:
        print("BLOCKED: is_active is falsy")
        sys.exit(1)

    result = verify_password(password, user["hashed_password"])
    print(f"verify_password('{password}', hash) = {result}")

    if result:
        print("\nAll checks PASS — login should work.")
        print("If it still fails, the issue is session/cookie/SECRET_KEY related.")

        # Check if SECRET_KEY might be different between deploys
        try:
            secret = os.environ.get("SECRET_KEY", "NOT SET")
            print(f"SECRET_KEY env: {'SET (' + str(len(secret)) + ' chars)' if secret != 'NOT SET' else 'NOT SET'}")
        except:
            pass
