from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.database import db_conn
from app.auth_utils import verify_password, create_token, get_current_user
from app.i18n import login_t

bp = Blueprint("auth", __name__, url_prefix="/auth")

_SUPPORTED_LANGS = {"en", "es", "it", "ja", "pt"}

@bp.route("/set-lang", methods=["POST"])
def set_lang():
    """Store language choice in session for pre-login pages."""
    lang = request.form.get("lang", "en")
    if lang in _SUPPORTED_LANGS:
        session["lang"] = lang
        session.permanent = True
    return redirect(request.referrer or url_for("auth.login"))

@bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard.index"))

    lang = session.get("lang", "en")
    if lang not in _SUPPORTED_LANGS:
        lang = "en"

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")

        with db_conn() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email=?", (email,)
            ).fetchone()

        if not user:
            error = "Invalid email or password"
        elif not user["is_active"]:
            error = "Account is deactivated. Contact your administrator."
        elif not verify_password(password, user["hashed_password"]):
            error = "Invalid email or password"
        else:
            token = create_token(user["id"])
            session["auth_token"] = token
            session.permanent = True
            return redirect(url_for("dashboard.index"))

    def t(key):
        return login_t(key, lang)

    return render_template("auth/login.html", error=error, lang=lang, t=t)

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
