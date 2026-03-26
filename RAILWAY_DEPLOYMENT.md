# 🚂 Railway Deployment Guide

This guide shows you how to deploy OSERVA OFFICE to Railway.app.

---

## 📋 Prerequisites

- GitHub account
- Railway account (free tier available at railway.app)

---

## 🚀 Deployment Steps

### Step 1: Push to GitHub

1. **Create a new repository on GitHub:**
   - Go to: https://github.com/new
   - Name it: `oserva-office`
   - Set to **Private** (recommended for business app)
   - Do NOT initialize with README

2. **Open VS Code in your project folder**

3. **Initialize Git and push:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit - OSERVA OFFICE"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/oserva-office.git
   git push -u origin main
   ```

   Replace `YOUR_USERNAME` with your GitHub username.

---

### Step 2: Deploy to Railway

1. **Go to Railway:**
   - Visit: https://railway.app
   - Click "Start a New Project"
   - Choose "Deploy from GitHub repo"
   - Authorize Railway to access your GitHub

2. **Select your repository:**
   - Find: `oserva-office`
   - Click to deploy

3. **Add PostgreSQL database:**
   - In Railway dashboard, click "+ New"
   - Select "Database" → "Add PostgreSQL"
   - Railway will automatically set `DATABASE_URL` environment variable

4. **Set environment variables:**
   - Click on your app service
   - Go to "Variables" tab
   - Add these variables:

   ```
   SECRET_KEY = generate-random-32-char-string-here
   ACCESS_TOKEN_EXPIRE_MINUTES = 480
   DEBUG = false
   UPLOAD_DIR = app/static/uploads
   MAX_UPLOAD_SIZE_MB = 20
   ```

   **Generate SECRET_KEY:**
   In VS Code terminal, run:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Copy the output and use it as SECRET_KEY.

5. **Create initial users:**
   After deployment, click on your app → "Settings" → "Generate Domain"
   
   Then in Railway, go to PostgreSQL database → "Data" tab → "Query"
   
   Run this SQL to create admin user:
   ```sql
   INSERT INTO users (email, full_name, hashed_password, role, job_title, avatar_color, is_active, created_at)
   VALUES (
     'admin@yourcompany.com',
     'Admin User',
     'pbkdf2:sha256:1000000$SALT$HASH',
     'admin',
     'System Administrator',
     '#6366f1',
     1,
     datetime('now')
   );
   ```

   **Better approach:** Use the Railway CLI to run seed script:
   ```bash
   railway run python seed.py
   ```

---

### Step 3: Access Your App

1. **Get your app URL:**
   - In Railway dashboard, click your app service
   - Click "Settings" → "Generate Domain"
   - You'll get a URL like: `https://oserva-office-production.up.railway.app`

2. **Login:**
   - Go to: `https://your-app.railway.app/auth/login`
   - Use seed credentials:
     - Admin: `elena@oserva.com` / `password123`
     - Owner: `marco@oserva.com` / `password123`

3. **Create your real admin:**
   - Login as admin
   - Go to Settings → New User
   - Create your production admin account
   - Logout and login with new account
   - Delete seed users for security

---

## 🔧 Local Development with VS Code

### Setup:

1. **Open project in VS Code**

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment:**
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Create .env file:**
   Copy `.env.example` to `.env` and edit:
   ```
   DATABASE_URL=sqlite:///./oserva.db
   SECRET_KEY=your-local-secret-key
   DEBUG=true
   ```

6. **Initialize database:**
   ```bash
   python seed.py
   ```

7. **Run development server:**
   ```bash
   python run.py
   ```

8. **Access locally:**
   http://localhost:5000/auth/login

---

## 📝 VS Code Recommended Extensions

Install these for better development experience:

- **Python** (Microsoft) - Python language support
- **Pylance** (Microsoft) - Python IntelliSense
- **Jinja** (wholroyd) - Jinja2 template syntax highlighting
- **SQLite Viewer** (alexcvzz) - View database contents
- **GitLens** (GitKraken) - Git integration

---

## 🔐 Security Notes

### Before Production:

1. **Change SECRET_KEY** - Use a strong random 32+ character string
2. **Remove seed users** - Delete demo accounts after creating real ones
3. **Enable HTTPS** - Railway provides this automatically
4. **Set strong passwords** - For all production users
5. **Review permissions** - Ensure role-based access is correct

### After Deployment:

1. **Test all features** - Go through each module
2. **Create backup strategy** - Export PostgreSQL database regularly
3. **Monitor logs** - Check Railway logs for errors
4. **Set up alerts** - Use Railway's monitoring features

---

## 🐛 Troubleshooting

### Database connection errors:

**Problem:** `could not connect to server`

**Solution:** Make sure PostgreSQL service is running in Railway and DATABASE_URL is set.

---

### Static files not loading:

**Problem:** CSS/JS files return 404

**Solution:** Railway serves static files automatically. Make sure `app/static/` folder is in Git.

---

### "Module not found" errors:

**Problem:** Import errors on Railway

**Solution:** Check `requirements.txt` has all dependencies. Railway auto-installs from this file.

---

### Can't login after deployment:

**Problem:** Login redirects back to login page

**Solution:** 
1. Check SECRET_KEY is set in Railway variables
2. Make sure DATABASE_URL is configured (PostgreSQL)
3. Run `railway run python seed.py` to create users

---

## 📊 Database Management

### View database contents:

**In Railway:**
- Go to PostgreSQL service → "Data" tab
- Use Query editor to run SQL

**Locally with VS Code:**
- Install "SQLite Viewer" extension
- Right-click `oserva.db` → "Open Database"

### Backup database:

**Railway (PostgreSQL):**
```bash
railway run pg_dump $DATABASE_URL > backup.sql
```

**Local (SQLite):**
Just copy the `oserva.db` file

---

## 🔄 Updating Your Deployment

1. **Make changes in VS Code**

2. **Test locally:**
   ```bash
   python run.py
   ```

3. **Commit and push:**
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin main
   ```

4. **Railway auto-deploys** - Check deployment logs in Railway dashboard

---

## 📞 Support

- **Railway Docs:** https://docs.railway.app
- **GitHub Issues:** Create issues in your repository
- **Railway Discord:** https://discord.gg/railway

---

## ✅ Checklist

Before going live:

- [ ] Database (PostgreSQL) added to Railway
- [ ] SECRET_KEY environment variable set (random 32+ chars)
- [ ] Domain generated in Railway
- [ ] Seed script run to create initial users
- [ ] Demo users deleted after creating real admin
- [ ] All modules tested (Cases, Calendar, Documents, etc.)
- [ ] SSL/HTTPS working (automatic with Railway)
- [ ] Backup strategy in place
- [ ] Team members invited and roles assigned

---

**Your app is now production-ready!** 🚀
