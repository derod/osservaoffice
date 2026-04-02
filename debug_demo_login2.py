#!/usr/bin/env python3
"""Debug: simulate the exact login route flow and test hash storage round-trip."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db_conn
from app.auth_utils import hash_password, verify_password

email = "demo@osservaoffice.com"
password = "demo"

# Step 1: Generate a fresh hash and immediately verify it
fresh_hash = hash_password(password)
print(f"Fresh hash: {fresh_hash}")
print(f"Fresh hash length: {len(fresh_hash)}")
print(f"Verify fresh (in-memory): {verify_password(password, fresh_hash)}")

with db_conn() as conn:
    # Step 2: Write the fresh hash
    conn.execute("UPDATE users SET hashed_password = ? WHERE email = ?", (fresh_hash, email))

with db_conn() as conn:
    # Step 3: Read it back in a NEW connection and verify
    user = conn.execute("SELECT id, email, hashed_password FROM users WHERE email = ?", (email,)).fetchone()

    if not user:
        print(f"NOT FOUND: {email}")
        rows = conn.execute("SELECT id, email FROM users WHERE email LIKE ?", ("%demo%",)).fetchall()
        print(f"LIKE search: {[dict(r) for r in rows]}")
        sys.exit(1)

    stored = user["hashed_password"]
    print(f"\nStored hash: {stored}")
    print(f"Stored hash length: {len(stored)}")
    print(f"Hashes match exactly: {fresh_hash == stored}")
    print(f"Verify from DB: {verify_password(password, stored)}")

    # Step 4: Check for hidden chars
    if fresh_hash != stored:
        print(f"\nMISMATCH!")
        print(f"Fresh repr: {repr(fresh_hash)}")
        print(f"Stored repr: {repr(stored)}")
    else:
        print(f"\nHash round-trip OK. Password 'demo' verified against DB.")

    # Step 5: Also verify other working user for comparison
    rod = conn.execute("SELECT id, email, hashed_password FROM users WHERE email = ?", ("rodgabriel12@gmail.com",)).fetchone()
    if rod:
        print(f"\nComparison - rodgabriel12 hash length: {len(rod['hashed_password'])}")
        print(f"rodgabriel12 hash prefix: {rod['hashed_password'][:30]}")
        print(f"demo hash prefix:         {stored[:30]}")
