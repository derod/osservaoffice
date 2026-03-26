# ARCHITECTURE.md

> Describes how OSSERVA OFFICE is built -- module responsibilities, data flow, and technology choices.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Web Framework | Flask 3.x |
| Database | SQLite (WAL mode) |
| Auth | itsdangerous URLSafeTimedSerializer + werkzeug password hashing |
| Templating | Jinja2 (server-rendered) |
| CSS | Tailwind CSS (CDN) + custom pulse-grid.css |
| Icons | Font Awesome 6 (CDN) |
| WSGI Server (prod) | Gunicorn |
| Process File | Procfile: gunicorn -w 4 -b 0.0.0.0:$PORT run:app |

---

## File Structure

```
OSERVA_OFFICE_MERGED/
|-- run.py                  Entry point -- calls create_app(), runs dev server
|-- seed.py                 Populates DB with demo data for development
|-- Procfile                Production process command (Railway/Heroku)
|-- requirements.txt        Python dependencies
|-- .env / .env.example     Environment configuration
|
+-- app/
    |-- __init__.py         Flask app factory (create_app)
    |-- database.py         Schema, init_db(), db_conn() context manager
    |-- auth_utils.py       Token creation/verification, decorators, password utils
    |
    |-- routes/
    |   |-- __init__.py     Empty
    |   |-- auth.py         Blueprint: login, logout
    |   |-- dashboard.py    Blueprint: main dashboard
    |   |-- cases.py        Blueprint: case board, detail, tasks, key dates
    |   |-- calendar.py     Blueprint: appointments CRUD
    |   |-- employees.py    Blueprint: staff list, individual agenda
    |   |-- announcements.py Blueprint: team announcements
    |   +-- other.py        Five blueprints in one file:
    |                         avail_bp     /availability
    |                         sr_bp        /schedule-requests
    |                         docs_bp      /documents
    |                         clients_bp   /clients
    |                         settings_bp  /settings
    |
    |-- templates/
    |   |-- base.html                 Master layout (sidebar, topbar, theme)
    |   |-- auth/login.html           Standalone (does not extend base.html)
    |   |-- dashboard/index.html
    |   |-- cases/board.html          Kanban columns
    |   |-- cases/detail.html         Case view with tasks, docs, activity
    |   |-- cases/form.html
    |   |-- calendar/index.html       Day / week / list view
    |   |-- calendar/form.html
    |   |-- employees/list.html       Staff directory with status badges
    |   |-- employees/agenda.html
    |   |-- clients/list.html
    |   |-- clients/detail.html
    |   |-- clients/form.html
    |   |-- announcements/index.html
    |   |-- availability/index.html   Horizontal timeline with % positioning
    |   |-- schedule_requests/list.html
    |   |-- schedule_requests/form.html
    |   |-- documents/list.html
    |   |-- settings/index.html       Profile + language + user table
    |   |-- settings/user_form.html
    |   +-- partials/error.html
    |
    +-- static/
        |-- css/pulse-grid.css        Custom theme with CSS variables
        +-- uploads/                  User-uploaded files (UUID-named)
```

---

## Application Factory (app/__init__.py)

create_app() is the single entry point for Flask initialization:

1. Creates the Flask instance pointing to app/templates and app/static.
2. Loads config from environment variables (SECRET_KEY, PERMANENT_SESSION_LIFETIME, MAX_CONTENT_LENGTH).
3. Calls init_db() -- creates tables and applies column migrations on every startup.
4. Registers 11 blueprints from the routes modules.
5. Injects Jinja2 globals used across all templates:
   - format_dt, format_time, format_date -- datetime display formatting
   - is_overdue -- boolean check against current time
   - duration_mins -- appointment duration in minutes
   - top_px, height_px -- pixel offsets for calendar grid layout
   - get_initials -- generates "JD" from "John Doe"
   - now -- datetime.utcnow() for templates
6. Registers GET /health returning {"status": "ok"}.

---

## Database Layer (app/database.py)

- db_conn() -- context manager. Opens WAL-mode SQLite with foreign keys enabled.
  Commits on success, rolls back on exception, always closes.
- init_db() -- runs CREATE TABLE IF NOT EXISTS for all 10 tables, then applies
  ALTER TABLE migrations guarded by PRAGMA table_info checks.
- No ORM. All queries are raw SQL strings via conn.execute().
- Rows accessed by column name via sqlite3.Row row factory.

### Tables

| Table | Purpose |
|---|---|
| users | Accounts with role, avatar color, language preference |
| clients | Client directory |
| cases | Legal cases with status, priority, Kanban fields |
| case_assignments | Many-to-many join: cases and users |
| appointments | Calendar events |
| tasks | Case-scoped checklist items |
| schedule_requests | Time-off/meeting requests with approval workflow |
| documents | File upload metadata (not the files themselves) |
| activity_logs | Case audit trail |
| announcements | Team-wide notices |

---

## Authentication Layer (app/auth_utils.py)

Login POST:
  verify_password(plain, hashed) via werkzeug check_password_hash (pbkdf2:sha256)
  create_token(user_id) via URLSafeTimedSerializer(SECRET_KEY).dumps(user_id)
  session["auth_token"] = token, session.permanent = True (8-hour lifetime)

Every protected request via @login_required:
  get_current_user()
    verify_token() -- serializer.loads(token, max_age=480*60)
    get_user_by_id(user_id)
    check is_active == 1
    g.user = dict(user_row)

Decorators:
  @login_required  -- redirects to login if no valid session
  @admin_required  -- redirects if role not in (admin, owner)

---

## Request / Response Flow

```
Browser POST/GET
  1. @login_required validates session, sets g.user
  2. Route reads g.user["role"] for access control
  3. db_conn() context manager opens connection
  4. SQL query executed, results as list of dicts
  5. render_template() called with data
  6. Jinja2 renders HTML using base.html
  7. HTML response or redirect returned
```

---

## Frontend Architecture

- No JavaScript framework. All rendering is server-side via Jinja2.
- Tailwind CSS from CDN. Custom overrides in static/css/pulse-grid.css.
- Font Awesome 6 from CDN for all icons.
- Modals implemented as inline dialog/div toggled by minimal vanilla JS inside templates.
- Theme toggle (light/dark) stores class on html element in localStorage.
- Avatar initials rendered via get_initials() Jinja global inside colored div circles.
- Calendar grid uses CSS top/height percentage positioning from top_px()/height_px() globals.
- Availability timeline uses percentage-based left/width inline styles (to_pct, to_width_pct).

---

## Blueprint URL Map

| Blueprint | Prefix | File |
|---|---|---|
| auth_bp | /auth | routes/auth.py |
| dashboard_bp | (none) | routes/dashboard.py |
| cases_bp | /cases | routes/cases.py |
| calendar_bp | /calendar | routes/calendar.py |
| employees_bp | /employees | routes/employees.py |
| announcements_bp | /announcements | routes/announcements.py |
| avail_bp | /availability | routes/other.py |
| sr_bp | /schedule-requests | routes/other.py |
| docs_bp | /documents | routes/other.py |
| clients_bp | /clients | routes/other.py |
| settings_bp | /settings | routes/other.py |

---

## Deployment

- Gunicorn entry point: run:app (the app object returned by create_app() in run.py).
- Health check: GET /health returns {"status": "ok"} (used by Railway uptime checks).
- DATABASE_PATH env var controls SQLite file location.
- UPLOAD_DIR env var controls file storage path.
- Database is initialized on every startup. Safe to re-run due to IF NOT EXISTS guards.
