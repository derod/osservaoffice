# OSERVA OFFICE - Quick Start Guide

## ✅ Complete Working Application

This is a **fully functional** law firm office management system ready to run immediately.

## 🚀 Installation (3 Simple Steps)

### Step 1: Extract Files
```bash
tar -xzf oserva_office.tar.gz
cd oserva_office
```

### Step 2: Seed Database
```bash
python3 seed.py
```

### Step 3: Run Application
```bash
python3 run.py
```

Visit: **http://localhost:5000/auth/login**

## 🔑 Demo Accounts (All Functional!)

| Role | Email | Password |
|------|-------|----------|
| **Owner** | marco@oserva.com | password123 |
| **Admin** | elena@oserva.com | password123 |
| **Staff** | luca@oserva.com | password123 |
| **Staff** | sofia@oserva.com | password123 |

## 👥 Creating New Users

### Method 1: Admin Panel (Recommended)
1. Login as Admin (elena@oserva.com)
2. Go to **Settings** (bottom of sidebar)
3. Click **New User** button
4. Fill in: Name, Email, Password, Role
5. Click **Create**

### Method 2: Python Script
```bash
python3 -c "
from app.database import db_conn
from app.auth_utils import hash_password

with db_conn() as conn:
    conn.execute('''
        INSERT INTO users (email, full_name, hashed_password, role, job_title, avatar_color)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        'newuser@oserva.com',        # Email
        'New User Name',              # Full name
        hash_password('password123'), # Password (hashed)
        'staff',                      # Role: owner/admin/staff
        'Associate',                  # Job title
        '#6366f1'                     # Avatar color
    ))
print('✅ User created successfully!')
"
```

## 📁 Features Included

✅ **Dashboard** - Team overview with real-time status
✅ **Cases Board** - Kanban with open/in progress/waiting/closed columns
✅ **Case Management** - Detailed view with tasks, documents, activity log
✅ **Calendar** - Day/Week/List views with appointments
✅ **Team Directory** - Employee list with availability status
✅ **Availability Timeline** - Visual free/busy schedule
✅ **Schedule Requests** - Request & approve schedule changes
✅ **Document Management** - Upload, download, link to cases/clients
✅ **Client Directory** - Client profiles with cases and documents
✅ **Settings** - User management (Admin only) + profile editing

## 🔐 Role Permissions

| Feature | Owner | Admin | Staff |
|---------|-------|-------|-------|
| View Dashboard | ✅ | ✅ | ✅ |
| View All Cases | ✅ (read-only) | ✅ | Own cases only |
| Edit Cases | ❌ | ✅ | Assigned cases |
| Create Cases | ❌ | ✅ | ❌ |
| Approve Schedule Requests | ✅ | ✅ | ❌ |
| User Management | ❌ | ✅ | ❌ |
| Upload Documents | ✅ | ✅ | ✅ |
| Delete Documents | ❌ | ✅ | ❌ |

## 💾 Database

- **Engine:** SQLite (development) / PostgreSQL-ready (production)
- **Location:** `oserva.db` (auto-created)
- **Tables:** 8 tables (users, clients, cases, appointments, tasks, schedule_requests, documents, activity_logs)
- **Data:** Fully seeded with 7 users, 5 clients, 6 cases, 8 appointments, 6 tasks

## 🛠️ Tech Stack

- **Backend:** Flask 3.1 + Python 3.11+
- **Database:** SQLite3 (built-in, no installation needed)
- **Auth:** Werkzeug password hashing + itsdangerous JWT tokens
- **Templates:** Jinja2
- **UI:** TailwindCSS CDN + Font Awesome 6
- **Zero external dependencies** beyond Python standard library + Flask

## 📝 Notes

1. **No Registration Page** - This is intentional for security. New users must be created by admins through the Settings page.

2. **File Uploads** - Documents are stored in `app/static/uploads/` directory (auto-created).

3. **Session Duration** - 8 hours by default (configurable in `app/__init__.py`).

4. **Production Deployment** - For production use, set a strong `SECRET_KEY` environment variable and use a production WSGI server like Gunicorn.

## 🚨 Troubleshooting

### "Module not found" errors
```bash
pip3 install Flask Werkzeug itsdangerous Jinja2
```

### "Permission denied" on seed.py
```bash
chmod +x seed.py
python3 seed.py
```

### Port 5000 already in use
Edit `run.py` and change:
```python
app.run(debug=True, host="0.0.0.0", port=5000)  # Change 5000 to 5001
```

### Users can't login
Make sure you ran `python3 seed.py` first!

## 📧 Support

Built with Flask. All code is self-contained and documented.

**Everything works out of the box** - no configuration required!
