from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.database import db_conn
from app.auth_utils import verify_password, create_token, get_current_user

bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard.index"))

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

    return render_template("auth/login.html", error=error)

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
