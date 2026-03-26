# OSSERVA OFFICE

A web-based office management system for law firms. Built with Flask and SQLite.

---

## Quick Start (Local — Windows PowerShell)

```powershell
# 1. Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed the database (demo data with default login)
python seed.py

# 4. Run the app
python run.py
```

Open **http://localhost:5000** and log in with:
- **Email:** `elena@oserva.com`
- **Password:** `password123`

---

## Quick Start (Local — macOS / Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
python run.py
```

---

## Deploy to Railway

1. Push this project to a GitHub repo (make sure `venv/` is in `.gitignore`).
2. Create a new project on [Railway](https://railway.app/) and link the repo.
3. Set the following **environment variables** in Railway:

| Variable | Value |
|---|---|
| `SECRET_KEY` | A random string ≥ 32 chars (e.g. `openssl rand -hex 32`) |
| `FLASK_ENV` | `production` |
| `DATABASE_PATH` | `/app/oserva.db` (or use Railway's volume mount) |

4. Railway will auto-detect the `Procfile` and run:
   ```
   gunicorn -w 4 -b 0.0.0.0:$PORT run:app
   ```

5. **Health check:** `GET /health` returns `{"status": "ok"}` with HTTP 200.

---

## Project Structure

```
├── run.py                 # Entry point (gunicorn uses run:app)
├── Procfile               # Railway/Heroku process file
├── railway.json           # Railway config
├── requirements.txt       # Python dependencies
├── runtime.txt            # Python version
├── seed.py                # Database seeder with demo data
├── .env.example           # Environment variable template
├── app/
│   ├── __init__.py        # Flask app factory (create_app)
│   ├── auth_utils.py      # Authentication helpers
│   ├── database.py        # SQLite database init & connection
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py        # Login / logout
│   │   ├── dashboard.py   # Main dashboard
│   │   ├── cases.py       # Cases CRUD + Kanban
│   │   ├── calendar.py    # Calendar / appointments
│   │   ├── employees.py   # Employee directory + agendas
│   │   └── other.py       # Availability, schedule requests, documents, clients, settings
│   ├── templates/         # Jinja2 templates (responsive)
│   └── static/
│       ├── css/pulse-grid.css  # Theme CSS with CSS variables
│       └── uploads/       # Document uploads
```

---

## Notes

- **Database:** SQLite by default. Set `DATABASE_PATH` env var to control location.
- **Uploads:** Stored in `app/static/uploads/`. Set `UPLOAD_DIR` env var to change.
- **Auth:** Session-based with signed tokens (itsdangerous). Passwords hashed with pbkdf2:sha256.
- **No background processes** — the app boots cleanly for Railway.

---

## Core Features

| Module | Description |
|---|---|
| **Dashboard** | Stats: active cases, tasks today, appointments, pending requests. Team availability cards. |
| **Cases** | Kanban board (Open / Litigation / Closed). Tasks, key dates, activity log per case. |
| **Calendar** | Day / week / list view. Filter by employee and appointment type. |
| **Clients** | Client directory linked to cases and documents. |
| **Employees** | Staff directory with live free/busy status and individual agenda view. |
| **Availability** | Visual timeline of team availability across working hours (08:00–18:00). |
| **Schedule Requests** | Staff request time-off or meetings; admins approve (creates appointment) or deny. |
| **Documents** | File uploads (.pdf, .doc, .docx, .xls, .xlsx, images) linked to cases or clients. Max 20 MB. |
| **Announcements** | Team-wide notices with pin support. |
| **Settings** | User management, profile editing, interface language preference. |

---

## Roles

| Role | Capabilities |
|---|---|
| `owner` | Full read/write access. Cannot be assigned via UI — set directly in the database. |
| `admin` | Create/edit cases and users. Approve/deny schedule requests. Delete documents. |
| `staff` | View and edit only their assigned cases. View their own calendar and agenda only. |

---

## Who It Is For

Small to mid-size law firms needing an internal case management and team coordination tool without external cloud service dependencies.
