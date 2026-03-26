# SPEC.md — System Contract

> **This file defines how OSSERVA OFFICE MUST behave.**
> Before modifying any feature, read the relevant section here.
> Do not change behavior that contradicts this document without explicit approval.

---

## 1. Authentication & Session

### Flow
1. User submits email + password to `POST /auth/login`.
2. Password is verified against the `hashed_password` column using `werkzeug.security.check_password_hash` (pbkdf2:sha256).
3. On success, a `URLSafeTimedSerializer` token is created with the user's `id` as payload.
4. Token is stored in `session["auth_token"]`. Session is marked `permanent = True`.
5. Session lifetime is **8 hours** (`PERMANENT_SESSION_LIFETIME`).
6. On every protected request, the `@login_required` decorator calls `get_current_user()`:
   - Reads `session["auth_token"]`
   - Verifies token (max_age = 480 minutes)
   - Fetches the user row from the database
   - Checks `is_active = 1`
   - Sets `g.user = dict(user_row)` for use in templates and routes
7. If the token is missing, expired, or the user is inactive → redirect to `/auth/login`.

### Critical Rules
- **NEVER** store the raw password anywhere.
- **NEVER** bypass `@login_required` on any route that reads or writes user data.
- The `owner` role must **never** be assignable through the UI. It can only be set directly in the database.
- Inactive users (`is_active = 0`) must be blocked from logging in.

---

## 2. Role-Based Access Control

### Roles
| Role | String value | Access level |
|---|---|---|
| Owner | `owner` | Full access — equivalent to admin but cannot be created via UI |
| Admin | `admin` | Full access via UI |
| Staff | `staff` | Restricted — assigned cases and own calendar only |

### Enforcement Rules (DO NOT BREAK)

**Cases:**
- Staff may only view cases where a matching row exists in `case_assignments (case_id, user_id)`.
- Staff may only edit cases where they are assigned.
- Only `admin` or `owner` may create new cases.
- Only `admin` or `owner` may add/remove case assignments.

**Calendar:**
- Staff only see appointments where `assigned_to_user_id = g.user["id"]`.
- Only `admin` or `owner` may delete appointments.

**Employees / Agenda:**
- Staff may only view their own agenda (`/employees/<user_id>/agenda` where `user_id == g.user["id"]`).

**Schedule Requests:**
- Staff see only their own requests (`requested_employee_id = g.user["id"]`).
- Only `admin` or `owner` may approve or deny requests.
- Approving a request **must** create a corresponding appointment row.

**Documents:**
- Only `admin` may delete documents.

**Settings / Users:**
- Only `admin` or `owner` may access `/settings`.
- Only `admin` or `owner` may create or edit users.
- Any authenticated user may edit their own profile via `POST /settings/profile/edit`.

**Announcements:**
- Any authenticated user may create an announcement.
- Only `admin`, `owner`, or the announcement creator may delete an announcement.
- Only `admin` or `owner` may toggle the pin on an announcement.

---

## 3. Data Model Rules

### users
- `email` must be unique (enforced by DB constraint).
- `role` must be one of: `owner`, `admin`, `staff`.
- `language` must be one of: `en`, `es`, `it`, `ja`, `pt`. Defaults to `en`.
- `avatar_color` is a hex color string (e.g. `#6366f1`).
- `is_active` is `1` (active) or `0` (inactive). Inactive users cannot log in.

### cases
- `status` must be one of: `open`, `in_progress`, `waiting`, `closed`.
- `priority` must be one of: `low`, `medium`, `high`.
- Closing a case (`status = 'closed'`) sets `closed_at = datetime('now')`.
- Every status change must be logged to `activity_logs`.

### appointments
- `start_datetime` and `end_datetime` must be stored as `"YYYY-MM-DD HH:MM:SS"` strings.
- `assigned_to_user_id` is required (not nullable in practice).

### documents
- Allowed extensions: `.pdf .doc .docx .jpg .jpeg .png .gif .txt .xls .xlsx`
- Maximum file size: `MAX_UPLOAD_SIZE_MB` (default 20 MB).
- Files are stored as `{uuid4().hex}{ext}` inside `UPLOAD_DIR`.
- The `file_path` column stores the full filesystem path used for download and deletion.
- Deleting a document record **must** also delete the file from disk.

### schedule_requests
- `status` must be one of: `pending`, `approved`, `denied`.
- Approving sets `status = 'approved'`, records `approved_by_user_id`, `resolved_at`, and `created_appointment_id`.
- Denying sets `status = 'denied'`, records `denial_reason`, `approved_by_user_id`, `resolved_at`.

### activity_logs
- Every significant case mutation (status change, assignment change, edit) must insert a row into `activity_logs` with `user_id`, `case_id`, `action`, and `details`.

---

## 4. Database Rules

- **Engine:** SQLite with `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`.
- **Connection:** Always use the `db_conn()` context manager from `app/database.py`. Never open a raw connection.
- **Migrations:** New columns are added via `ALTER TABLE` inside `init_db()` with a `PRAGMA table_info` guard (check before altering). This pattern must be followed for every schema change.
- **No ORM.** All queries are raw SQL executed via `conn.execute()`.
- `conn.row_factory = sqlite3.Row` is set on every connection — rows can be accessed by column name.

---

## 5. File Upload Rules

- Validate extension against the `ALLOWED_EXT` set before writing to disk.
- Validate file size against `MAX_SIZE` (read full content into memory, check `len(contents)`).
- Generate a `uuid4().hex + ext` stored filename — never use the original filename for storage.
- `os.makedirs(UPLOAD_DIR, exist_ok=True)` is called before writing.
- On document deletion: delete the physical file (`os.remove`) before or after deleting the DB row, but both must happen.

---

## 6. Availability / Work Hours

- Work day is defined as `WORK_START = 8` to `WORK_END = 18` (hours, UTC).
- Availability timeline blocks are calculated as percentages of the 10-hour window.
- Busy blocks that extend outside the window are clamped to `[WORK_START, WORK_END]`.

---

## 7. Template & Jinja Context Rules

- All protected templates must receive `current_user=g.user` from the route.
- The `get_initials(name)` function is available as a Jinja2 global (registered in `create_app()`).
- Templates must not implement business logic — logic belongs in routes.
- `base.html` provides the full layout including sidebar, topbar, and theme toggle. All pages except `auth/login.html` must extend it.

---

## 8. Non-Goals

The following are explicitly **outside the scope** of this system:

- Email sending or notifications (no SMTP, no email templates).
- Background jobs or task queues.
- Multi-tenancy (single firm per deployment).
- PostgreSQL or any database other than SQLite (psycopg2 is in requirements.txt but unused).
- REST API endpoints (all routes return HTML or redirects).
- JavaScript frontend framework (no React, Vue, etc.).
- File preview (documents are download-only).
