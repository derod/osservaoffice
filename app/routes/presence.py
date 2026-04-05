"""
presence.py
HTTP endpoints for presence data.

Routes:
  GET /api/presence          → snapshot for current user's org (or all, if super_admin)
  GET /api/presence/<int:user_id> → single user's DB last_seen_at (offline fallback)
"""

from flask import Blueprint, jsonify, g
from app.auth_utils import login_required, org_id_for
from app.database import db_conn
from app.routes.presence_socket import get_presence_snapshot

bp = Blueprint("presence", __name__, url_prefix="/api/presence")


@bp.route("")
@login_required
def presence_snapshot():
    """Return current in-memory presence for the caller's org."""
    oid = org_id_for(g.user)  # None for super_admin → all orgs
    data = get_presence_snapshot(oid)
    return jsonify({"presence": data})


@bp.route("/<int:user_id>")
@login_required
def user_last_seen(user_id):
    """Return DB-persisted last_seen_at for a single user (offline fallback)."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT id, full_name, last_seen_at, organization_id FROM users WHERE id=?", (user_id,)
        ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    row = dict(row)
    # Non-super_admin can only see users in their own org
    oid = org_id_for(g.user)
    if oid and row.get("organization_id") != oid:
        return jsonify({"error": "not found"}), 404
    row.pop("organization_id", None)
    return jsonify(row)
