"""
database.py — dual-mode database layer (SQLite for local dev, PostgreSQL for production).

All route and service files use the same API:

    from app.database import db_conn, get_integration_setting, set_integration_setting

    with db_conn() as conn:
        row  = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        rows = conn.execute("SELECT * FROM users").fetchall()
        cur  = conn.execute("INSERT INTO users (...) VALUES (?,?,?)", (...))
        new_id = cur.lastrowid   # works on both backends

Rules for SQL written in route/service files:
  - Use  ?  as parameter placeholder (auto-translated to %s for psycopg2)
  - Use  datetime('now')  (auto-translated to NOW() for psycopg2)
  - Use  INSERT OR IGNORE  (auto-translated to INSERT ... ON CONFLICT DO NOTHING)
  - Row objects support both dict(row) and row["column"] access on both backends
  - conn.executescript(sql)  works on both backends (runs each statement separately)

Environment:
  DATABASE_URL   → PostgreSQL mode  (e.g. postgresql://user:pass@host/db)
  DATABASE_PATH  → SQLite mode      (default: osserva.db)
"""

import os
import re
import sqlite3
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Railway sometimes sets postgres:// which psycopg2 needs as postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_USE_PG = bool(DATABASE_URL)


# ---------------------------------------------------------------------------
# SQL translation helpers (SQLite dialect → PostgreSQL dialect)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\?")
_DATETIME_NOW_RE = re.compile(r"datetime\s*\(\s*'now'\s*\)", re.IGNORECASE)
_INSERT_OR_IGNORE_RE = re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)


def _pg_sql(sql: str) -> str:
    """Translate SQLite-dialect SQL to PostgreSQL dialect."""
    sql = _PLACEHOLDER_RE.sub("%s", sql)
    sql = _DATETIME_NOW_RE.sub("NOW()", sql)
    sql = _INSERT_OR_IGNORE_RE.sub("INSERT INTO", sql)
    # INSERT OR IGNORE becomes INSERT ... ON CONFLICT DO NOTHING
    # We append the clause only when the pattern was matched above
    if re.search(r"INSERT\s+INTO", sql, re.IGNORECASE) and "ON CONFLICT" not in sql.upper():
        # Only append DO NOTHING if it was originally an INSERT OR IGNORE
        pass  # handled in _PgCursor.execute via flag
    return sql


def _pg_sql_ignore(sql: str) -> tuple[str, bool]:
    """Return (translated_sql, was_insert_or_ignore)."""
    was_ignore = bool(_INSERT_OR_IGNORE_RE.search(sql))
    translated = _pg_sql(sql)
    if was_ignore and "ON CONFLICT" not in translated.upper():
        # Strip the trailing semicolon if any, then append
        translated = translated.rstrip("; \n") + " ON CONFLICT DO NOTHING"
    return translated, was_ignore


# ---------------------------------------------------------------------------
# PostgreSQL connection pool
# ---------------------------------------------------------------------------

_pg_pool = None


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import psycopg2.pool
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pg_pool


# ---------------------------------------------------------------------------
# Row wrappers
# ---------------------------------------------------------------------------

class _DictRow(dict):
    """dict subclass that also supports row["col"] and row[int_index] access,
    mimicking sqlite3.Row well enough for all existing route code."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):
        return super().keys()


# ---------------------------------------------------------------------------
# Cursor wrappers
# ---------------------------------------------------------------------------

class _PgCursor:
    """
    Wraps a psycopg2 cursor to match the sqlite3 cursor API used in routes:
      - .execute(sql, params) — translates ? → %s and datetime('now') → NOW()
      - .executemany(sql, seq)
      - .fetchone() / .fetchall() — return _DictRow objects
      - .lastrowid — populated via RETURNING id
      - .rowcount
    """

    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self._lastrowid = None

    def execute(self, sql: str, params=None):
        pg_sql, was_ignore = _pg_sql_ignore(sql)

        # If the statement is INSERT and doesn't already have RETURNING, add it
        # so we can populate lastrowid
        is_insert = re.match(r"\s*INSERT\s+", pg_sql, re.IGNORECASE)
        has_returning = "RETURNING" in pg_sql.upper()
        if is_insert and not has_returning:
            pg_sql = pg_sql.rstrip("; \n") + " RETURNING id"

        if params:
            self._cur.execute(pg_sql, params)
        else:
            self._cur.execute(pg_sql)

        # Grab the returned id for INSERT statements
        if is_insert and not has_returning:
            try:
                row = self._cur.fetchone()
                if row:
                    self._lastrowid = row[0] if isinstance(row, (list, tuple)) else row.get("id")
            except Exception:
                self._lastrowid = None
        return self

    def executemany(self, sql: str, seq):
        pg_sql, _ = _pg_sql_ignore(sql)
        self._cur.executemany(pg_sql, seq)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return _DictRow(row)
        # RealDictRow or tuple — convert
        desc = self._cur.description or []
        return _DictRow(zip([d[0] for d in desc], row))

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        desc = self._cur.description or []
        if isinstance(rows[0], dict):
            return [_DictRow(r) for r in rows]
        cols = [d[0] for d in desc]
        return [_DictRow(zip(cols, r)) for r in rows]

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __iter__(self):
        for row in self.fetchall():
            yield row


class _PgConnection:
    """
    Wraps a psycopg2 connection to present the sqlite3-compatible API
    used throughout the routes:
      - conn.execute(sql, params) → _PgCursor
      - conn.executescript(sql)   → runs each semicolon-delimited statement
      - conn.commit() / rollback()
    """

    def __init__(self, raw_conn):
        import psycopg2.extras
        self._conn = raw_conn
        # Use RealDictCursor so rows come back as dicts
        self._conn.cursor_factory = psycopg2.extras.RealDictCursor

    def execute(self, sql: str, params=None):
        cur = self._conn.cursor()
        wrapper = _PgCursor(cur)
        wrapper.execute(sql, params)
        return wrapper

    def executescript(self, sql: str):
        """Run multiple semicolon-separated statements (like sqlite3.executescript)."""
        cur = self._conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            translated = _pg_sql(stmt)
            try:
                cur.execute(translated)
            except Exception as e:
                # Log but continue — CREATE TABLE IF NOT EXISTS on existing tables
                # sometimes raises in strict mode; we re-raise for real errors
                import logging
                err_str = str(e).lower()
                if "already exists" in err_str or "duplicate" in err_str:
                    self._conn.rollback()
                    continue
                raise
        return self

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # returned to pool by the context manager — don't close directly
        pass

    def cursor(self):
        import psycopg2.extras
        return _PgCursor(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))


# ---------------------------------------------------------------------------
# SQLite connection wrapper (thin shim for lastrowid-via-RETURNING parity)
# ---------------------------------------------------------------------------

class _SqliteRow(sqlite3.Row):
    """sqlite3.Row already supports dict-like access; expose .get() too."""

    def get(self, key, default=None):
        try:
            return self[key]
        except (IndexError, KeyError):
            return default


class _SqliteCursorWrapper:
    """Thin wrapper around sqlite3 cursor so that fetchone/fetchall return
    objects that also have a .get() method (used in a few service files)."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return _DictRow(dict(row))

    def fetchall(self):
        return [_DictRow(dict(r)) for r in self._cur.fetchall()]

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __iter__(self):
        for row in self.fetchall():
            yield row


class _SqliteConnection:
    """Thin wrapper around sqlite3.Connection for API parity."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql: str, params=None):
        if params:
            cur = self._conn.execute(sql, params)
        else:
            cur = self._conn.execute(sql)
        return _SqliteCursorWrapper(cur)

    def executescript(self, sql: str):
        self._conn.executescript(sql)
        return self

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ---------------------------------------------------------------------------
# Public connection factory
# ---------------------------------------------------------------------------

def get_db_path():
    return os.environ.get("DATABASE_PATH", "osserva.db")


@contextmanager
def db_conn():
    """Context manager yielding a connection object compatible with both backends.

    Usage (unchanged from the original code):

        with db_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    """
    if _USE_PG:
        pool = _get_pg_pool()
        raw = pool.getconn()
        raw.autocommit = False
        conn = _PgConnection(raw)
        try:
            yield conn
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            pool.putconn(raw)
    else:
        raw = sqlite3.connect(get_db_path())
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        conn = _SqliteConnection(raw)
        try:
            yield conn
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE,
    plan TEXT NOT NULL DEFAULT 'trial',
    status TEXT NOT NULL DEFAULT 'active',
    is_active INTEGER NOT NULL DEFAULT 1,
    trial_ends_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    job_title TEXT,
    phone TEXT,
    avatar_color TEXT DEFAULT '#6366f1',
    is_active INTEGER DEFAULT 1,
    language TEXT DEFAULT 'en',
    hourly_rate REAL DEFAULT 0,
    organization_id INTEGER REFERENCES organizations(id),
    last_seen_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    company_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    client_id INTEGER REFERENCES clients(id),
    due_date TEXT,
    overview TEXT,
    current_step TEXT,
    next_action TEXT,
    blockers TEXT,
    closed_at TEXT,
    court_name TEXT,
    case_number TEXT,
    case_type TEXT DEFAULT 'Other',
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS case_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TEXT DEFAULT (datetime('now')),
    UNIQUE(case_id, user_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    start_datetime TEXT NOT NULL,
    end_datetime TEXT NOT NULL,
    assigned_to_user_id INTEGER REFERENCES users(id),
    case_id INTEGER REFERENCES cases(id),
    client_id INTEGER REFERENCES clients(id),
    location TEXT,
    meeting_link TEXT,
    appointment_type TEXT DEFAULT 'appointment',
    created_by_user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    is_completed INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'medium',
    assigned_to_user_id INTEGER REFERENCES users(id),
    case_id INTEGER REFERENCES cases(id),
    created_by_user_id INTEGER REFERENCES users(id),
    completed_at TEXT,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedule_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_employee_id INTEGER NOT NULL REFERENCES users(id),
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    request_type TEXT NOT NULL,
    requested_start_datetime TEXT NOT NULL,
    requested_end_datetime TEXT NOT NULL,
    reason TEXT,
    notes TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'pending',
    denial_reason TEXT,
    approved_by_user_id INTEGER REFERENCES users(id),
    resolved_at TEXT,
    created_appointment_id INTEGER REFERENCES appointments(id),
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    case_id INTEGER REFERENCES cases(id),
    client_id INTEGER REFERENCES clients(id),
    uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
    description TEXT,
    trashed_at TEXT,
    trashed_by_user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    case_id INTEGER REFERENCES cases(id),
    action TEXT NOT NULL,
    details TEXT,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS integration_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checked_in_at TEXT NOT NULL DEFAULT (datetime('now')),
    status        TEXT NOT NULL DEFAULT 'on_time',
    notes         TEXT,
    case_id       INTEGER REFERENCES cases(id),
    source        TEXT NOT NULL DEFAULT 'self',
    checked_out_at TEXT,
    checkout_status TEXT,
    checkout_notes TEXT,
    organization_id INTEGER REFERENCES organizations(id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id               INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    subject                 TEXT NOT NULL,
    body                    TEXT NOT NULL,
    is_read                 INTEGER NOT NULL DEFAULT 0,
    deleted_by_sender_at    TEXT,
    deleted_by_recipient_at TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gmail_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT UNIQUE NOT NULL,
    gmail_thread_id TEXT,
    subject TEXT,
    from_name TEXT,
    from_email TEXT,
    to_emails TEXT,
    cc_emails TEXT,
    snippet TEXT,
    body_text TEXT,
    received_at TEXT,
    has_pdf INTEGER DEFAULT 0,
    processed_status TEXT DEFAULT 'new',
    matched_client_id INTEGER REFERENCES clients(id),
    matched_case_id INTEGER REFERENCES cases(id),
    error_message TEXT,
    trashed_at TEXT,
    trashed_by_user_id INTEGER REFERENCES users(id),
    imported_at TEXT DEFAULT (datetime('now')),
    last_synced_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gmail_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT NOT NULL,
    gmail_attachment_id TEXT,
    filename TEXT,
    mime_type TEXT,
    file_size INTEGER,
    stored_filename TEXT,
    file_path TEXT,
    is_pdf INTEGER DEFAULT 0,
    extracted_text TEXT,
    document_id INTEGER REFERENCES documents(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gmail_sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_key TEXT UNIQUE NOT NULL,
    sync_value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS legal_chat_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    jurisdiction TEXT,
    subject_area TEXT,
    consultation_type TEXT,
    confidence_score REAL,
    mentor_mode INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS legal_chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES legal_chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jurisdiction_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    flag_emoji TEXT,
    system_prompt_extra TEXT,
    key_laws TEXT,
    court_structure TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS legal_case_studies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES legal_chat_conversations(id) ON DELETE SET NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    jurisdiction TEXT,
    subject_area TEXT,
    summary TEXT,
    outcome TEXT,
    lessons_learned TEXT,
    is_peer_validated INTEGER DEFAULT 0,
    validated_by_user_id INTEGER REFERENCES users(id),
    validated_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS demo_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    firm_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    country TEXT,
    team_size TEXT,
    interest_type TEXT NOT NULL,
    current_software TEXT,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    pipeline_stage TEXT NOT NULL DEFAULT 'new',
    source TEXT DEFAULT 'website',
    assigned_to_name TEXT,
    follow_up_date TEXT,
    conversion_notes TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_PG_DDL = """
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE,
    plan TEXT NOT NULL DEFAULT 'trial',
    status TEXT NOT NULL DEFAULT 'active',
    is_active INTEGER NOT NULL DEFAULT 1,
    trial_ends_at TEXT,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    job_title TEXT,
    phone TEXT,
    avatar_color TEXT DEFAULT '#6366f1',
    is_active INTEGER DEFAULT 1,
    language TEXT DEFAULT 'en',
    hourly_rate REAL DEFAULT 0,
    organization_id INTEGER REFERENCES organizations(id),
    last_seen_at TEXT,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    company_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    client_id INTEGER REFERENCES clients(id),
    due_date TEXT,
    overview TEXT,
    current_step TEXT,
    next_action TEXT,
    blockers TEXT,
    closed_at TEXT,
    court_name TEXT,
    case_number TEXT,
    case_type TEXT DEFAULT 'Other',
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS case_assignments (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(case_id, user_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    start_datetime TEXT NOT NULL,
    end_datetime TEXT NOT NULL,
    assigned_to_user_id INTEGER REFERENCES users(id),
    case_id INTEGER REFERENCES cases(id),
    client_id INTEGER REFERENCES clients(id),
    location TEXT,
    meeting_link TEXT,
    appointment_type TEXT DEFAULT 'appointment',
    created_by_user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    is_completed INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'medium',
    assigned_to_user_id INTEGER REFERENCES users(id),
    case_id INTEGER REFERENCES cases(id),
    created_by_user_id INTEGER REFERENCES users(id),
    completed_at TEXT,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS schedule_requests (
    id SERIAL PRIMARY KEY,
    requested_employee_id INTEGER NOT NULL REFERENCES users(id),
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    request_type TEXT NOT NULL,
    requested_start_datetime TEXT NOT NULL,
    requested_end_datetime TEXT NOT NULL,
    reason TEXT,
    notes TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'pending',
    denial_reason TEXT,
    approved_by_user_id INTEGER REFERENCES users(id),
    resolved_at TEXT,
    created_appointment_id INTEGER REFERENCES appointments(id),
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    case_id INTEGER REFERENCES cases(id),
    client_id INTEGER REFERENCES clients(id),
    uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
    description TEXT,
    trashed_at TEXT,
    trashed_by_user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    case_id INTEGER REFERENCES cases(id),
    action TEXT NOT NULL,
    details TEXT,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    organization_id INTEGER REFERENCES organizations(id),
    created_at TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS integration_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS checkins (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checked_in_at   TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    status          TEXT NOT NULL DEFAULT 'on_time',
    notes           TEXT,
    case_id         INTEGER REFERENCES cases(id),
    source          TEXT NOT NULL DEFAULT 'self',
    checked_out_at  TEXT,
    checkout_status TEXT,
    checkout_notes  TEXT,
    organization_id INTEGER REFERENCES organizations(id),
    created_at      TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS messages (
    id                      SERIAL PRIMARY KEY,
    sender_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id               INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    subject                 TEXT NOT NULL,
    body                    TEXT NOT NULL,
    is_read                 INTEGER NOT NULL DEFAULT 0,
    deleted_by_sender_at    TEXT,
    deleted_by_recipient_at TEXT,
    created_at              TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS gmail_messages (
    id SERIAL PRIMARY KEY,
    gmail_message_id TEXT UNIQUE NOT NULL,
    gmail_thread_id TEXT,
    subject TEXT,
    from_name TEXT,
    from_email TEXT,
    to_emails TEXT,
    cc_emails TEXT,
    snippet TEXT,
    body_text TEXT,
    received_at TEXT,
    has_pdf INTEGER DEFAULT 0,
    processed_status TEXT DEFAULT 'new',
    matched_client_id INTEGER REFERENCES clients(id),
    matched_case_id INTEGER REFERENCES cases(id),
    error_message TEXT,
    trashed_at TEXT,
    trashed_by_user_id INTEGER REFERENCES users(id),
    imported_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    last_synced_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS gmail_attachments (
    id SERIAL PRIMARY KEY,
    gmail_message_id TEXT NOT NULL,
    gmail_attachment_id TEXT,
    filename TEXT,
    mime_type TEXT,
    file_size INTEGER,
    stored_filename TEXT,
    file_path TEXT,
    is_pdf INTEGER DEFAULT 0,
    extracted_text TEXT,
    document_id INTEGER REFERENCES documents(id),
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS gmail_sync_state (
    id SERIAL PRIMARY KEY,
    sync_key TEXT UNIQUE NOT NULL,
    sync_value TEXT,
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS legal_chat_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    jurisdiction TEXT,
    subject_area TEXT,
    consultation_type TEXT,
    confidence_score REAL,
    mentor_mode INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS legal_chat_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES legal_chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS jurisdiction_profiles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    flag_emoji TEXT,
    system_prompt_extra TEXT,
    key_laws TEXT,
    court_structure TEXT,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS legal_case_studies (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES legal_chat_conversations(id) ON DELETE SET NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    jurisdiction TEXT,
    subject_area TEXT,
    summary TEXT,
    outcome TEXT,
    lessons_learned TEXT,
    is_peer_validated INTEGER DEFAULT 0,
    validated_by_user_id INTEGER REFERENCES users(id),
    validated_at TEXT,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS demo_requests (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    firm_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    country TEXT,
    team_size TEXT,
    interest_type TEXT NOT NULL,
    current_software TEXT,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    pipeline_stage TEXT NOT NULL DEFAULT 'new',
    source TEXT DEFAULT 'website',
    assigned_to_name TEXT,
    follow_up_date TEXT,
    conversion_notes TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
);
"""


def _column_exists_pg(conn, table: str, column: str) -> bool:
    """Check if a column exists in a PostgreSQL table."""
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        (table, column),
    ).fetchone()
    return row is not None


def _run_pg_migrations(conn):
    """Idempotent column additions for PostgreSQL (mirrors the SQLite PRAGMA migrations)."""
    migrations = [
        # (table, column, definition)
        ("cases",                     "court_name",               "TEXT"),
        ("cases",                     "case_number",              "TEXT"),
        ("users",                     "language",                 "TEXT DEFAULT 'en'"),
        ("users",                     "hourly_rate",              "REAL DEFAULT 0"),
        ("checkins",                  "case_id",                  "INTEGER REFERENCES cases(id)"),
        ("checkins",                  "source",                   "TEXT NOT NULL DEFAULT 'self'"),
        ("checkins",                  "checked_out_at",           "TEXT"),
        ("checkins",                  "checkout_status",          "TEXT"),
        ("checkins",                  "checkout_notes",           "TEXT"),
        ("messages",                  "deleted_by_sender_at",     "TEXT"),
        ("messages",                  "deleted_by_recipient_at",  "TEXT"),
        ("documents",                 "trashed_at",               "TEXT"),
        ("documents",                 "trashed_by_user_id",       "INTEGER REFERENCES users(id)"),
        ("gmail_messages",            "trashed_at",               "TEXT"),
        ("gmail_messages",            "trashed_by_user_id",       "INTEGER REFERENCES users(id)"),
        ("legal_chat_conversations",  "subject_area",             "TEXT"),
        ("legal_chat_conversations",  "consultation_type",        "TEXT"),
        ("legal_chat_conversations",  "confidence_score",         "REAL"),
        ("legal_chat_conversations",  "mentor_mode",              "INTEGER DEFAULT 0"),
        # Multi-tenant org columns
        ("users",           "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("clients",         "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("cases",           "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("appointments",    "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("tasks",           "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("schedule_requests","organization_id", "INTEGER REFERENCES organizations(id)"),
        ("documents",       "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("activity_logs",   "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("announcements",   "organization_id",  "INTEGER REFERENCES organizations(id)"),
        ("checkins",        "organization_id",  "INTEGER REFERENCES organizations(id)"),
        # Demo requests lead management columns
        ("demo_requests",   "notes",            "TEXT"),
        ("demo_requests",   "updated_at",       "TEXT"),
        # Lead pipeline extended fields
        ("demo_requests",   "pipeline_stage",   "TEXT NOT NULL DEFAULT 'new'"),
        ("demo_requests",   "source",           "TEXT DEFAULT 'website'"),
        ("demo_requests",   "assigned_to_name", "TEXT"),
        ("demo_requests",   "follow_up_date",   "TEXT"),
        ("demo_requests",   "conversion_notes", "TEXT"),
        # Presence tracking
        ("users",           "last_seen_at",     "TEXT"),
        # Case type for legal classification
        ("cases",           "case_type",        "TEXT DEFAULT 'Other'"),
    ]
    for table, column, definition in migrations:
        if not _column_exists_pg(conn, table, column):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except Exception:
                pass  # column may have been added by DDL above


def _run_sqlite_migrations(conn):
    """Idempotent column additions for SQLite (ALTER TABLE ADD COLUMN is safe to skip if exists)."""
    _ORG_REF = "INTEGER REFERENCES organizations(id)"
    migrations = [
        ("users",            "organization_id", _ORG_REF),
        ("clients",          "organization_id", _ORG_REF),
        ("cases",            "organization_id", _ORG_REF),
        ("appointments",     "organization_id", _ORG_REF),
        ("tasks",            "organization_id", _ORG_REF),
        ("schedule_requests","organization_id", _ORG_REF),
        ("documents",        "organization_id", _ORG_REF),
        ("activity_logs",    "organization_id", _ORG_REF),
        ("announcements",    "organization_id", _ORG_REF),
        ("checkins",         "organization_id", _ORG_REF),
        # Demo requests lead management columns
        ("demo_requests",    "notes",           "TEXT"),
        ("demo_requests",    "updated_at",      "TEXT"),
        # Lead pipeline extended fields
        ("demo_requests",    "pipeline_stage",  "TEXT NOT NULL DEFAULT 'new'"),
        ("demo_requests",    "source",          "TEXT DEFAULT 'website'"),
        ("demo_requests",    "assigned_to_name","TEXT"),
        ("demo_requests",    "follow_up_date",  "TEXT"),
        ("demo_requests",    "conversion_notes","TEXT"),
        # Presence tracking
        ("users",            "last_seen_at",    "TEXT"),
        # Case type for legal classification
        ("cases",            "case_type",       "TEXT DEFAULT 'Other'"),
    ]
    for table, column, definition in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except Exception:
            pass  # column already exists


_HOT_INDEXES = [
    # (index_name, table, columns) — created with IF NOT EXISTS, safe on both backends.
    ("idx_users_org",          "users",         "organization_id"),
    ("idx_clients_org",        "clients",       "organization_id"),
    ("idx_cases_org",          "cases",         "organization_id"),
    ("idx_cases_org_status",   "cases",         "organization_id, status"),
    ("idx_appts_org",          "appointments",  "organization_id"),
    ("idx_appts_case",         "appointments",  "case_id"),
    ("idx_tasks_org",          "tasks",         "organization_id"),
    ("idx_tasks_case",         "tasks",         "case_id"),
    ("idx_docs_org",           "documents",     "organization_id"),
    ("idx_actlog_org",         "activity_logs", "organization_id"),
    ("idx_actlog_case",        "activity_logs", "case_id"),
    ("idx_msgs_recipient",     "messages",      "recipient_id, is_read"),
    ("idx_checkins_org",       "checkins",      "organization_id"),
]


def _create_hot_indexes(conn):
    """Idempotent. Skips silently if a referenced table/column doesn't exist yet."""
    for name, table, cols in _HOT_INDEXES:
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})")
        except Exception:
            pass


def init_db():
    """Create all tables. Idempotent — safe to call on every startup."""
    if _USE_PG:
        import psycopg2
        raw = psycopg2.connect(DATABASE_URL)
        raw.autocommit = False
        conn = _PgConnection(raw)
        try:
            # Run each CREATE TABLE IF NOT EXISTS separately
            for stmt in _PG_DDL.split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                try:
                    raw_cur = raw.cursor()
                    raw_cur.execute(stmt)
                except Exception as e:
                    err = str(e).lower()
                    if "already exists" in err:
                        raw.rollback()
                    else:
                        raw.rollback()
                        raise
            raw.commit()
            # Column migrations for databases that existed before this DDL
            conn2 = _PgConnection(raw)
            _run_pg_migrations(conn2)
            _create_hot_indexes(conn2)
            raw.commit()
        finally:
            raw.close()
    else:
        with db_conn() as conn:
            conn.executescript(_SQLITE_DDL)
            _run_sqlite_migrations(conn)
            _create_hot_indexes(conn)
    print("Database initialized")


# ---------------------------------------------------------------------------
# Integration settings helpers (unchanged public API)
# ---------------------------------------------------------------------------

def get_integration_setting(key: str) -> str | None:
    """Return the stored value for an integration setting key, or None."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT value FROM integration_settings WHERE key=?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_integration_setting(key: str, value: str) -> None:
    """Upsert an integration setting."""
    with db_conn() as conn:
        if _USE_PG:
            conn.execute("""
                INSERT INTO integration_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
            """, (key, value))
        else:
            conn.execute("""
                INSERT INTO integration_settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value))


# ---------------------------------------------------------------------------
# Organization helpers
# ---------------------------------------------------------------------------

def get_or_create_default_org(conn) -> int:
    """Return the id of the default organization, creating it if none exists."""
    row = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, plan, status, is_active) VALUES (?,?,?,?,?)",
        ("Default Organization", "default", "trial", "active", 1),
    )
    return cur.lastrowid


def assign_orphan_records(conn, org_id: int):
    """Back-fill organization_id on existing rows that predate multi-tenancy.
    super_admin users are intentionally left with organization_id=NULL."""
    # Users — skip super_admin (they float above all orgs)
    conn.execute(
        "UPDATE users SET organization_id=? WHERE organization_id IS NULL AND role != 'super_admin'",
        (org_id,),
    )
    other_tables = [
        "clients", "cases", "appointments", "tasks",
        "schedule_requests", "documents", "activity_logs", "announcements", "checkins",
    ]
    for table in other_tables:
        conn.execute(
            f"UPDATE {table} SET organization_id=? WHERE organization_id IS NULL",
            (org_id,),
        )
