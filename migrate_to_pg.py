"""
migrate_to_pg.py — one-shot SQLite → PostgreSQL data migration.

Usage:
    DATABASE_URL=postgresql://... DATABASE_PATH=osserva.db python migrate_to_pg.py

What it does:
  1. Reads every row from the local SQLite database.
  2. Inserts them into the already-initialised PostgreSQL database.
  3. Resets PostgreSQL SERIAL sequences so auto-increment continues from the
     correct value after the import.
  4. Skips tables that are already populated (re-entrant safe for most tables).

Run ONCE before going live. After migration, do not run again with live data.
"""

import os
import sys
import sqlite3

# Require both connection strings
SQLITE_PATH = os.environ.get("DATABASE_PATH", "osserva.db")
PG_URL = os.environ.get("DATABASE_URL", "")

if not PG_URL:
    sys.exit("ERROR: DATABASE_URL environment variable is not set.")

if not os.path.exists(SQLITE_PATH):
    sys.exit(f"ERROR: SQLite file not found at '{SQLITE_PATH}'.")

# Normalise Railway postgres:// prefix
if PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

import psycopg2
import psycopg2.extras

# Tables in dependency order (parents before children)
TABLES = [
    "users",
    "clients",
    "cases",
    "case_assignments",
    "appointments",
    "tasks",
    "schedule_requests",
    "documents",
    "activity_logs",
    "announcements",
    "integration_settings",
    "checkins",
    "messages",
    "gmail_messages",
    "gmail_attachments",
    "gmail_sync_state",
    "legal_chat_conversations",
    "legal_chat_messages",
    "jurisdiction_profiles",
    "legal_case_studies",
]

# Tables whose PK is a SERIAL and need sequence reset after import
SERIAL_TABLES = [t for t in TABLES if t != "integration_settings"]


def get_sqlite_rows(sqlite_conn, table):
    cur = sqlite_conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


def pg_table_empty(pg_conn, table):
    cur = pg_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0] == 0


def migrate_table(sqlite_conn, pg_conn, table):
    cols, rows = get_sqlite_rows(sqlite_conn, table)
    if not rows:
        print(f"  {table}: 0 rows (skipped)")
        return 0

    if not pg_table_empty(pg_conn, table):
        print(f"  {table}: already has data — skipping (drop table and re-run to reimport)")
        return 0

    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    cur = pg_conn.cursor()
    # Convert sqlite3.Row objects to plain tuples
    data = [tuple(row) for row in rows]
    psycopg2.extras.execute_batch(cur, sql, data, page_size=500)
    print(f"  {table}: {len(data)} rows migrated")
    return len(data)


def reset_sequences(pg_conn):
    """After bulk import with explicit IDs, reset SERIAL sequences."""
    cur = pg_conn.cursor()
    for table in SERIAL_TABLES:
        try:
            # Find the sequence name for the 'id' column
            cur.execute("""
                SELECT pg_get_serial_sequence(%s, 'id')
            """, (table,))
            row = cur.fetchone()
            if not row or not row[0]:
                continue
            seq = row[0]
            cur.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1))")
            print(f"  sequence reset: {seq}")
        except Exception as e:
            print(f"  WARNING: could not reset sequence for {table}: {e}")
            pg_conn.rollback()


def main():
    print(f"Connecting to SQLite: {SQLITE_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    print(f"Connecting to PostgreSQL: {PG_URL[:40]}...")
    pg_conn = psycopg2.connect(PG_URL)
    pg_conn.autocommit = False

    total = 0
    try:
        print("\n--- Migrating tables ---")
        for table in TABLES:
            try:
                total += migrate_table(sqlite_conn, pg_conn, table)
            except Exception as e:
                print(f"  ERROR on {table}: {e}")
                pg_conn.rollback()
                raise

        print("\n--- Resetting sequences ---")
        reset_sequences(pg_conn)

        pg_conn.commit()
        print(f"\nDone. {total} total rows migrated.")

    except Exception as e:
        pg_conn.rollback()
        print(f"\nMigration FAILED: {e}")
        sys.exit(1)
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
