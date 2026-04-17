import os
from flask import Flask, render_template, redirect, url_for, jsonify
from flask_socketio import SocketIO
from datetime import datetime, timedelta

# Single SocketIO instance — imported by live_room_socket and run.py
socketio = SocketIO()


def _bootstrap_super_admin():
    """Create or upgrade a super_admin user from env vars (idempotent).
    super_admin has no organization_id — they float above all tenants."""
    sa_email = os.environ.get("SUPER_ADMIN_EMAIL", "").strip().lower()
    sa_password = os.environ.get("SUPER_ADMIN_PASSWORD", "").strip()
    sa_name = os.environ.get("SUPER_ADMIN_NAME", "").strip()
    if not sa_email or not sa_password:
        return
    if not sa_name:
        sa_name = "Super Admin"

    from app.database import db_conn
    from app.auth_utils import hash_password

    with db_conn() as conn:
        existing = conn.execute("SELECT id, role FROM users WHERE email = ?", (sa_email,)).fetchone()
        if existing:
            if existing["role"] != "super_admin":
                # Upgrade role and clear org (super_admin is org-less)
                conn.execute(
                    "UPDATE users SET role = 'super_admin', organization_id = NULL WHERE id = ?",
                    (existing["id"],)
                )
                print(f"[super_admin] Upgraded existing user '{sa_email}' to super_admin.")
            else:
                print(f"[super_admin] User '{sa_email}' already has super_admin role.")
        else:
            conn.execute(
                "INSERT INTO users (full_name, email, hashed_password, role, is_active) "
                "VALUES (?, ?, ?, 'super_admin', 1)",
                (sa_name, sa_email, hash_password(sa_password)),
            )
            print(f"[super_admin] Created new super_admin user '{sa_email}'.")


def _bootstrap_default_org():
    """Ensure a default organization exists and all pre-existing data is assigned to it."""
    from app.database import db_conn, get_or_create_default_org, assign_orphan_records

    # Read org name from env so admins can label the default org on first run
    org_name = os.environ.get("DEFAULT_ORG_NAME", "").strip() or "Default Organization"

    with db_conn() as conn:
        # Update the name if it was set in env and the org already exists with the placeholder name
        org_id = get_or_create_default_org(conn)
        existing_name = conn.execute(
            "SELECT name FROM organizations WHERE id=?", (org_id,)
        ).fetchone()
        if existing_name and existing_name["name"] == "Default Organization" and org_name != "Default Organization":
            conn.execute("UPDATE organizations SET name=? WHERE id=?", (org_name, org_id))
        assign_orphan_records(conn, org_id)
    print(f"[org] Default organization id={org_id}.")


def create_app():
    app = Flask(__name__,
        template_folder="templates",
        static_folder="static"
    )

    # Browser cache for /static/* (1 day). Bust with ?v=... query string when needed.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400

    # Gzip responses (HTML/JSON/CSS/JS) — opt-in if package is installed.
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass

    # --- Secret key ---
    secret = os.environ.get("SECRET_KEY")
    env = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT") or ""
    if env.lower() in ("prod", "production") and not secret:
        raise RuntimeError("SECRET_KEY is required in production. Set it in Railway/Azure env vars.")
    app.secret_key = secret or "dev-only-change-me-not-for-production"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "20")) * 1024 * 1024
    is_production = env.lower() in ("prod", "production")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_production

    # --- Ensure upload directory exists ---
    _upload_dir = os.environ.get(
        "UPLOAD_DIR",
        os.path.join(os.path.dirname(__file__), "static", "uploads"),
    )
    try:
        os.makedirs(_upload_dir, exist_ok=True)
    except OSError as _e:
        print(f"[uploads] Could not create upload dir '{_upload_dir}': {_e}")

    # --- Health check (no auth, no DB) ---
    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # --- Init DB ---
    from app.database import init_db
    with app.app_context():
        init_db()

    # --- Bootstrap super_admin from env vars ---
    try:
        with app.app_context():
            _bootstrap_super_admin()
    except Exception as _e:
        print(f"[super_admin] Bootstrap skipped: {_e}")

    # --- Bootstrap default org and assign orphan records ---
    try:
        with app.app_context():
            _bootstrap_default_org()
    except Exception as _e:
        print(f"[org] Bootstrap skipped: {_e}")

    # --- Register blueprints ---
    from app.routes.auth import bp as auth_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.cases import bp as cases_bp
    from app.routes.calendar import bp as calendar_bp
    from app.routes.employees import bp as employees_bp
    from app.routes.other import (
        avail_bp, sr_bp, docs_bp, clients_bp, settings_bp, finances_bp, logins_bp
    )
    from app.routes.announcements import bp as announcements_bp
    from app.routes.inbox import bp as inbox_bp
    from app.routes.gmail_inbox import bp as gmail_inbox_bp
    from app.routes.legal_consultant import bp as legal_consultant_bp
    from app.routes.trash import bp as trash_bp
    from app.routes.live_room import bp as live_room_bp
    from app.routes.live_room_socket import register_socket_events
    from app.routes.public import bp as public_bp
    from app.routes.organizations import bp as organizations_bp
    from app.routes.presence import bp as presence_bp
    from app.routes.presence_socket import register_presence_events

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(avail_bp)
    app.register_blueprint(sr_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(announcements_bp)
    app.register_blueprint(finances_bp)
    app.register_blueprint(logins_bp)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(gmail_inbox_bp)
    app.register_blueprint(legal_consultant_bp)
    app.register_blueprint(trash_bp)
    app.register_blueprint(live_room_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(organizations_bp)
    app.register_blueprint(presence_bp)

    # ── SocketIO ───────────────────────────────────────────────
    # gevent is required under GeventWebSocketWorker (Railway/Gunicorn).
    # For local dev (python run.py / Flask dev server) use threading.
    _env = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT") or ""
    _async_mode = "gevent" if _env.lower() in ("prod", "production") else "threading"
    socketio.init_app(
        app,
        cors_allowed_origins="same_origin",
        async_mode=_async_mode,
        logger=False,
        engineio_logger=False,
    )
    register_socket_events(socketio)
    register_presence_events(socketio)

    # --- Template globals ---
    def get_initials(name):
        if not name:
            return "?"
        parts = name.strip().split()
        return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else parts[0][:2].upper()

    def format_dt(dt_val, fmt="%b %d, %Y"):
        if not dt_val:
            return "—"
        if isinstance(dt_val, str):
            try:
                dt_val = datetime.strptime(dt_val[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return dt_val
        return dt_val.strftime(fmt)

    def format_time(dt_val):
        if not dt_val:
            return "—"
        if isinstance(dt_val, str):
            try:
                dt_val = datetime.strptime(dt_val[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return dt_val
        return dt_val.strftime("%I:%M %p").lstrip("0")

    def format_size(size):
        if not size:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def dt_hour(dt_str):
        if not dt_str:
            return 0
        try:
            return datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S").hour
        except Exception:
            return 0

    def dt_minute(dt_str):
        if not dt_str:
            return 0
        try:
            return datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S").minute
        except Exception:
            return 0

    def dt_date(dt_str):
        if not dt_str:
            return ""
        try:
            return datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        except Exception:
            return dt_str[:10] if dt_str else ""

    def dt_time_input(dt_str):
        if not dt_str:
            return "09:00"
        try:
            return datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
        except Exception:
            return "09:00"

    def is_overdue(dt_str):
        if not dt_str:
            return False
        try:
            dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
            return dt < datetime.utcnow()
        except Exception:
            return False

    def duration_mins(start_str, end_str):
        try:
            s = datetime.strptime(start_str[:19], "%Y-%m-%d %H:%M:%S")
            e = datetime.strptime(end_str[:19], "%Y-%m-%d %H:%M:%S")
            return max(0, int((e - s).total_seconds() / 60))
        except Exception:
            return 0

    def top_px(dt_str, work_start=7):
        if not dt_str:
            return 0
        try:
            dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
            return (dt.hour - work_start) * 64 + int(dt.minute * 64 / 60)
        except Exception:
            return 0

    def height_px(start_str, end_str):
        mins = duration_mins(start_str, end_str)
        return max(28, int(mins * 64 / 60))

    def dt_weekday(dt_str):
        if not dt_str:
            return ""
        return dt_str[:10]

    from app.i18n import translate as _translate

    app.jinja_env.globals.update(
        get_initials=get_initials,
        format_dt=format_dt,
        format_time=format_time,
        format_size=format_size,
        dt_hour=dt_hour,
        dt_minute=dt_minute,
        dt_date=dt_date,
        dt_time_input=dt_time_input,
        is_overdue=is_overdue,
        duration_mins=duration_mins,
        top_px=top_px,
        height_px=height_px,
        dt_weekday=dt_weekday,
        now=datetime.utcnow,
        _=_translate,
    )

    @app.context_processor
    def inject_defaults():
        user = None
        unread = 0
        current_org = None
        try:
            from flask import g as _g
            user = getattr(_g, "user", None)
            if user:
                from app.database import db_conn
                with db_conn() as conn:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE recipient_id = ? AND is_read = 0",
                        (user["id"],)
                    ).fetchone()
                    unread = row[0] if row else 0
                    # Inject current org (None for super_admin)
                    if user.get("organization_id"):
                        org_row = conn.execute(
                            "SELECT * FROM organizations WHERE id=?",
                            (user["organization_id"],)
                        ).fetchone()
                        current_org = dict(org_row) if org_row else None
        except Exception:
            pass
        return {
            "active_nav": "",
            "current_user": user,
            "inbox_unread": unread,
            "current_org": current_org,
        }

    # Auto-purge expired trash items (lightweight check — once per hour)
    _last_purge = [None]

    @app.before_request
    def _maybe_auto_purge():
        now = datetime.utcnow()
        if _last_purge[0] and (now - _last_purge[0]).total_seconds() < 3600:
            return
        _last_purge[0] = now
        try:
            from app.services.trash_service import auto_purge_expired
            auto_purge_expired()
        except Exception:
            pass

    @app.errorhandler(404)
    def not_found(e):
        return render_template("partials/error.html", code=404, message="Page not found"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("partials/error.html", code=403, message="Access denied"), 403

    return app
