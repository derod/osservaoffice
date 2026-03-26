# PROMPTS.md -- Safe AI Development Guide

> Use this file when asking an AI assistant (Claude, GPT, etc.) to modify OSSERVA OFFICE.
> Following these patterns prevents regressions and keeps the system consistent.

---

## Universal Safe Development Prompt

Copy this as the opening of any AI session working on this project:

```
You are working on OSSERVA OFFICE, a Flask + SQLite law firm management system.

Before making any changes, read:
- SPEC.md for behavioral contracts and critical rules
- ARCHITECTURE.md for how the system is structured
- The specific route file and template you are modifying

Rules you must follow:
1. Do not change authentication or session logic unless the task explicitly requires it.
2. Do not add new database columns without adding an ALTER TABLE migration in init_db() in database.py, guarded by a PRAGMA table_info check.
3. Do not bypass @login_required or @admin_required decorators.
4. Do not introduce JavaScript frameworks -- the frontend is server-rendered Jinja2 + vanilla JS only.
5. Do not change role names (owner, admin, staff) or their access rules without updating SPEC.md.
6. All SQL must go through the db_conn() context manager from app/database.py.
7. Read the file before editing it.
8. Make the smallest change that satisfies the requirement.
```

---

## Feature Addition Prompts

### Add a new field to an existing form

```
I want to add a [field_name] field (type: TEXT/INTEGER) to the [table_name] table.

Steps needed:
1. Add ALTER TABLE migration to init_db() in app/database.py with PRAGMA table_info guard.
2. Add the input to the template at app/templates/[section]/form.html.
3. Update the INSERT and UPDATE SQL in app/routes/[file].py to include the new field.
4. Display the field in the detail/list template if needed.

Follow the existing pattern in the file. Do not change any other fields.
```

### Add a new page / section

```
I want to add a new section called [name] with URL prefix /[prefix].

Requirements:
- Create a new Blueprint in app/routes/[name].py following the pattern in app/routes/cases.py.
- Register the blueprint in app/__init__.py alongside the other blueprints.
- Create templates in app/templates/[name]/.
- All routes must use @login_required.
- Admin-only routes must check g.user["role"] in ("admin", "owner") or use @admin_required.
- Add a nav link to base.html in the sidebar, matching the existing style.
- Read ARCHITECTURE.md and SPEC.md before starting.
```

### Add a new role permission

```
I want to allow [role] users to [action].

Before changing anything:
1. Read SPEC.md section 2 (Role-Based Access Control).
2. Identify every route that currently blocks this action.
3. Update only the role check in those specific routes.
4. Update SPEC.md to document the new permission.
5. Do not change any other access rules.
```

---

## Bug Fix Prompts

### Route returns wrong data

```
The route [GET/POST] [url] is returning incorrect data.

Please:
1. Read the full route function in app/routes/[file].py.
2. Read the template it renders.
3. Identify the SQL query that produces the wrong result.
4. Fix only the query. Do not change the template or other routes.
5. Verify the fix does not break the role-based filtering (staff vs admin).
```

### Session / login issue

```
Users are being logged out unexpectedly / cannot log in.

Please:
1. Read app/auth_utils.py in full.
2. Read the @login_required decorator.
3. Check SECRET_KEY is set in the environment (not hardcoded).
4. Do not change the token serialization algorithm or session key name.
5. Only fix the specific failure described.
```

### Database error on startup

```
The app crashes during init_db() with a database error.

Please:
1. Read app/database.py init_db() in full.
2. Identify the failing statement.
3. If adding a column that already exists: add a PRAGMA table_info guard.
4. If a table is missing: add CREATE TABLE IF NOT EXISTS.
5. Do not change existing table definitions or column types.
```

---

## UI Change Prompts

### Modify a template

```
I want to change the appearance of [page name] at app/templates/[path].

Please:
1. Read the full template file before editing.
2. Use Tailwind CSS utility classes consistent with the rest of the file.
3. Do not add new CSS files or import new libraries.
4. Do not move logic from the route into the template.
5. Do not change form field names -- they must match what the route expects.
6. Keep all @url_for() references intact.
```

### Add a UI component to all pages

```
I want to add [component] to the shared layout.

Please:
1. Read app/templates/base.html in full.
2. Add the component in the appropriate section (sidebar / topbar / main).
3. Do not change the sidebar nav link structure or the active_nav logic.
4. Do not add JavaScript frameworks.
5. Keep the mobile-responsive layout intact (Tailwind responsive prefixes).
```

---

## Rules to Avoid Breaking the System

| Rule | Why |
|---|---|
| Always read the file before editing | Prevents overwriting unrelated logic |
| Never change form field names in templates | Route handlers reference them by exact name |
| Never rename blueprint variables or URL prefixes | url_for() calls throughout templates depend on them |
| Never remove db_conn() context manager | Raw connections skip WAL mode and foreign keys |
| Never hardcode SECRET_KEY | Breaks session tokens across restarts |
| Always add ALTER TABLE with PRAGMA guard | Prevents crash if column already exists |
| Never skip @login_required on any route | Exposes private data |
| Never store uploaded files under their original name | UUID naming prevents path traversal attacks |
| Never check role with == "admin" alone | Always use in ("admin", "owner") to include owner |
| Always log case mutations to activity_logs | Required for audit trail per SPEC.md |

---

## Quick Reference: Key Files to Read Before Editing

| Task | Files to read first |
|---|---|
| Auth / login changes | app/auth_utils.py, app/routes/auth.py |
| Case logic | app/routes/cases.py, SPEC.md section 2 |
| Calendar / appointments | app/routes/calendar.py |
| User/settings | app/routes/other.py (settings_bp section) |
| Database schema change | app/database.py (init_db full function) |
| Shared layout change | app/templates/base.html |
| New route/blueprint | app/__init__.py, ARCHITECTURE.md |
| File upload change | app/routes/other.py (docs_bp section), SPEC.md section 5 |
