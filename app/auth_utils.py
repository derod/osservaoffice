import os
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from functools import wraps
from flask import session, redirect, url_for, g, current_app
from app.database import db_conn

TOKEN_MAX_AGE = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480")) * 60


def _get_serializer():
    """Get serializer using Flask app's secret key (consistent with session signing)."""
    return URLSafeTimedSerializer(current_app.secret_key)


def hash_password(password: str) -> str:
    return generate_password_hash(password, method='pbkdf2:sha256')


def verify_password(password: str, hashed: str) -> bool:
    return check_password_hash(hashed, password)


def create_token(user_id: int) -> str:
    return _get_serializer().dumps({"uid": user_id})


def verify_token(token: str):
    try:
        data = _get_serializer().loads(token, max_age=TOKEN_MAX_AGE)
        return data.get("uid")
    except (SignatureExpired, BadSignature):
        return None


def get_user_by_id(user_id: int):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id=? AND is_active=1", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_current_user():
    token = session.get("auth_token")
    if not token:
        return None
    uid = verify_token(token)
    if not uid:
        return None
    return get_user_by_id(uid)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("auth.login"))
        g.user = user
        return f(*args, **kwargs)
    return decorated


def is_super_admin(user) -> bool:
    """True if user has the super_admin role."""
    if not user:
        return False
    return user.get("role") == "super_admin"


def is_admin_like(user) -> bool:
    """True if user has admin, owner, or super_admin role."""
    if not user:
        return False
    return user.get("role") in ("admin", "owner", "super_admin")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("auth.login"))
        if user["role"] not in ("admin", "owner", "super_admin"):
            return redirect(url_for("dashboard.index"))
        g.user = user
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("auth.login"))
        if user["role"] != "super_admin":
            return redirect(url_for("dashboard.index"))
        g.user = user
        return f(*args, **kwargs)
    return decorated


def get_initials(name: str) -> str:
    if not name:
        return "?"
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


# ---------------------------------------------------------------------------
# Organization / tenant helpers
# ---------------------------------------------------------------------------

def get_current_org(user: dict):
    """Return the organization dict for the given user, or None for super_admin."""
    if not user:
        return None
    if user.get("role") == "super_admin":
        return None  # super_admin has no single org
    org_id = user.get("organization_id")
    if not org_id:
        return None
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
    return dict(row) if row else None


def org_id_for(user: dict):
    """Return the organization_id for the current user. None for super_admin (sees all)."""
    if not user:
        return None
    if user.get("role") == "super_admin":
        return None
    return user.get("organization_id")


def org_filter(user: dict, alias: str = "") -> tuple[str, list]:
    """Return a WHERE/AND clause fragment and params to scope queries to the user's org.

    Usage:
        clause, params = org_filter(g.user, alias="c")
        rows = conn.execute(f"SELECT * FROM cases c WHERE 1=1{clause}", params).fetchall()

    super_admin: returns empty clause (sees all orgs).
    All others:  returns ' AND <alias.>organization_id = ?' with the user's org_id.
    """
    oid = org_id_for(user)
    if oid is None:
        return "", []
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}organization_id = ?", [oid]
