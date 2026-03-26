# 🚀 Quick Start with VS Code & Railway

**This guide assumes you're using VS Code and deploying to Railway.**

---

## 📦 Step 1: Open in VS Code

1. Extract the ZIP file
2. Open VS Code
3. File → Open Folder → Select `oserva-office` folder

---

## 🔧 Step 2: Local Development Setup

### In VS Code Terminal (Ctrl + `):

```bash
# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
copy .env.example .env    # Windows
# or
cp .env.example .env      # Mac/Linux

# Initialize database with demo users
python seed.py

# Run the app
python run.py
```

**Open browser:** http://localhost:5000/auth/login

**Login:** elena@oserva.com / password123

---

## 🌐 Step 3: Deploy to Railway

### A. Push to GitHub:

```bash
# In VS Code Terminal:
git init
git add .
git commit -m "Initial commit"
git branch -M main

# Go to https://github.com/new and create a repository named: oserva-office
# Then run:
git remote add origin https://github.com/YOUR_USERNAME/oserva-office.git
git push -u origin main
```

### B. Deploy on Railway:

1. Go to https://railway.app
2. Click "Start a New Project"
3. Select "Deploy from GitHub repo"
4. Choose your `oserva-office` repository
5. Click "+ New" → "Database" → "Add PostgreSQL"

### C. Set Environment Variables:

In Railway dashboard → Your app → Variables tab:

```
SECRET_KEY = [Generate random 32-char string]
ACCESS_TOKEN_EXPIRE_MINUTES = 480
DEBUG = false
UPLOAD_DIR = app/static/uploads
MAX_UPLOAD_SIZE_MB = 20
```

**To generate SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### D. Create Initial Users:

After deployment, in Railway dashboard:

1. Click on your app service
2. Go to "Settings" → "Generate Domain"
3. Note your app URL (e.g., `https://oserva-office-production.up.railway.app`)

**Create admin user via Railway CLI:**

```bash
# Install Railway CLI:
npm install -g @railway/cli

# Login:
railway login

# Link to your project:
railway link

# Run seed script:
railway run python seed.py
```

Or manually create user in PostgreSQL → Data → Query:

```sql
-- Replace the hash with a properly generated one
INSERT INTO users (email, full_name, hashed_password, role, job_title, avatar_color, is_active)
VALUES (
  'admin@yourcompany.com',
  'Your Name',
  'pbkdf2:sha256:1000000$GENERATED_HASH',
  'admin',
  'Administrator',
  '#6366f1',
  1
);
```

---

## ✅ Step 4: Access Your App

1. Open: `https://your-app.railway.app/auth/login`
2. Login with seed credentials
3. Go to Settings → Create your real admin user
4. Logout and login with new account
5. Delete seed users

---

## 🎯 Creating New Users (Production)

### Method 1 - Web Interface (Easiest):

1. Login as admin
2. Click "Settings" (left sidebar)
3. Click "New User" button
4. Fill form:
   - Email
   - Password
   - Role (owner/admin/staff)
5. Submit

### Method 2 - Python Script:

```python
from app.database import db_conn
from app.auth_utils import hash_password

with db_conn() as conn:
    conn.execute('''
        INSERT INTO users (email, full_name, hashed_password, role, job_title, avatar_color)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        'newuser@company.com',
        'User Full Name',
        hash_password('secure_password'),
        'staff',  # or 'admin' or 'owner'
        'Job Title',
        '#6366f1'
    ))
    print("✅ User created!")
```

---

## 🐛 Troubleshooting

### VS Code Python not found:

1. Ctrl+Shift+P → "Python: Select Interpreter"
2. Choose the one in `venv` folder

### Module not found errors:

```bash
# Make sure venv is activated (should see (venv) in terminal)
pip install -r requirements.txt
```

### Railway build fails:

- Check `requirements.txt` is in root folder
- Make sure `Procfile` exists
- Verify PostgreSQL is added as a service

### Can't login after Railway deployment:

1. Check DATABASE_URL is set (automatic with PostgreSQL)
2. Verify SECRET_KEY is set in Variables
3. Run `railway run python seed.py` to create users

---

## 📚 Useful Commands

```bash
# Local development:
python run.py                    # Start server
python seed.py                   # Create demo users

# Git:
git status                       # Check changes
git add .                        # Stage all changes
git commit -m "message"          # Commit
git push                         # Push to GitHub (auto-deploys to Railway)

# Railway CLI:
railway login                    # Authenticate
railway link                     # Link to project
railway run python seed.py       # Run commands on Railway
railway logs                     # View logs
```

---

## 📁 Key Files

- `run.py` - Application entry point
- `seed.py` - Creates demo users & data
- `requirements.txt` - Python dependencies
- `Procfile` - Tells Railway how to start app
- `railway.json` - Railway configuration
- `.env` - Local environment variables (DO NOT commit!)
- `.env.example` - Template for .env
- `RAILWAY_DEPLOYMENT.md` - Detailed deployment guide
- `README.md` - Full documentation

---

## ✨ You're Done!

**Local:** http://localhost:5000/auth/login  
**Production:** https://your-app.railway.app/auth/login

**Admin:** elena@oserva.com / password123 (seed user - delete after setup)

---

**Need help?** Check `RAILWAY_DEPLOYMENT.md` for detailed guide.
