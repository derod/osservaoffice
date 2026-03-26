# OSERVA OFFICE - Windows Setup Guide

## ❌ Issue: "no se encontró Python"

This means Python is not installed or not in your system PATH.

## ✅ Solution: Install Python

### Step 1: Download Python
1. Go to: https://www.python.org/downloads/
2. Download **Python 3.11** or **Python 3.12**
3. **IMPORTANT:** During installation, CHECK the box: **"Add Python to PATH"**

### Step 2: Verify Installation
Open PowerShell or Command Prompt:
```powershell
python --version
```

Should show: `Python 3.11.x` or `Python 3.12.x`

### Step 3: Install Flask (if needed)
```powershell
pip install Flask Werkzeug itsdangerous Jinja2
```

### Step 4: Run the Application
```powershell
cd Desktop\Kimi_Agent_OSERVA_Office_SaaS_Development\oserva-office
python seed.py
python run.py
```

### Step 5: Open Browser
Visit: http://localhost:5000/auth/login

---

## 🚀 Alternative: Use Python from Microsoft Store

If the above doesn't work:

1. Open **Microsoft Store**
2. Search for **"Python 3.12"**
3. Click **Install**
4. Wait for installation
5. Open **PowerShell** and run:
```powershell
cd Desktop\Kimi_Agent_OSERVA_Office_SaaS_Development\oserva-office
python seed.py
python run.py
```

---

## 🔑 Login Credentials

After running `python seed.py`, use these accounts:

| Role | Email | Password |
|------|-------|----------|
| **Admin** | elena@oserva.com | password123 |
| **Owner** | marco@oserva.com | password123 |
| **Staff** | luca@oserva.com | password123 |

---

## 📝 To Create New Users

1. Login as **Admin** (elena@oserva.com)
2. Click **Settings** in the left sidebar
3. Click **"New User"** button
4. Fill in the form:
   - Full Name
   - Email
   - Password
   - Role (owner/admin/staff)
5. Click **"Create"**

---

## ⚠️ Common Windows Issues

### Issue: "pip is not recognized"
**Solution:** Reinstall Python and CHECK "Add Python to PATH"

### Issue: Port 5000 already in use
**Solution:** Edit `run.py` line 6:
```python
app.run(debug=True, host="0.0.0.0", port=5001)  # Changed from 5000 to 5001
```

### Issue: "ModuleNotFoundError: No module named 'flask'"
**Solution:**
```powershell
pip install Flask Werkzeug itsdangerous Jinja2
```

---

## 📁 Your File Structure Should Look Like:

```
oserva-office/
├── app/
│   ├── __init__.py
│   ├── auth_utils.py
│   ├── database.py
│   ├── routes/
│   └── templates/
├── seed.py          ← Run this first
├── run.py           ← Then run this
├── requirements.txt
└── README.md
```

---

## ✅ Quick Test

After Python is installed, run these commands one by one:

```powershell
# 1. Check Python works
python --version

# 2. Navigate to project
cd Desktop\Kimi_Agent_OSERVA_Office_SaaS_Development\oserva-office

# 3. Install dependencies (if not already)
pip install Flask

# 4. Create database & demo users
python seed.py

# 5. Start server
python run.py

# 6. Open browser to:
# http://localhost:5000/auth/login
```

---

## 🆘 Still Not Working?

Try using `py` instead of `python`:

```powershell
py seed.py
py run.py
```

Or use the full path to Python:

```powershell
C:\Users\rodss\AppData\Local\Programs\Python\Python312\python.exe seed.py
```

---

## 🎉 Once Running

The application will show:
```
✅ Database initialized
🌱 Seeding database...
✅ Seed complete!

📋 Login credentials:
  Owner : marco@oserva.com  / password123
  Admin : elena@oserva.com  / password123
  Staff : luca@oserva.com   / password123

🚀 Run: python run.py

 * Running on http://127.0.0.1:5000
```

Press `Ctrl+C` to stop the server.
