from flask import Blueprint, render_template, request, redirect, url_for, g, abort
from app.auth_utils import login_required, is_admin_like, org_filter, org_id_for
from app.database import db_conn
from datetime import datetime

bp = Blueprint("announcements", __name__, url_prefix="/announcements")


@bp.route("")
@login_required
def index():
    oc, op = org_filter(g.user, alias="a")
    with db_conn() as conn:
        rows = conn.execute(
            f"""SELECT a.*, u.full_name as author_name, u.avatar_color
            FROM announcements a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE 1=1{oc}
            ORDER BY a.is_pinned DESC, a.created_at DESC""",
            op
        ).fetchall()
    return render_template("announcements/index.html",
        current_user=g.user,
        announcements=[dict(r) for r in rows],
    )


@bp.route("/new", methods=["POST"])
@login_required
def create():
    f = request.form
    title = f.get("title", "").strip()
    content = f.get("content", "").strip()
    if not title or not content:
        return redirect(url_for("announcements.index"))

    oid = org_id_for(g.user)
    with db_conn() as conn:
        conn.execute("""
            INSERT INTO announcements (user_id, title, content, is_pinned, organization_id)
            VALUES (?, ?, ?, 0, ?)
        """, (g.user["id"], title, content, oid))
    return redirect(url_for("announcements.index"))


@bp.route("/<int:ann_id>/pin", methods=["POST"])
@login_required
def toggle_pin(ann_id):
    if not is_admin_like(g.user):
        abort(403)
    oc, op = org_filter(g.user)
    with db_conn() as conn:
        row = conn.execute(
            f"SELECT is_pinned FROM announcements WHERE id=?{oc}", [ann_id] + op
        ).fetchone()
        if not row:
            abort(404)
        conn.execute("UPDATE announcements SET is_pinned=? WHERE id=?",
                     (0 if row["is_pinned"] else 1, ann_id))
    return redirect(url_for("announcements.index"))


@bp.route("/<int:ann_id>/delete", methods=["POST"])
@login_required
def delete(ann_id):
    oc, op = org_filter(g.user)
    with db_conn() as conn:
        row = conn.execute(
            f"SELECT user_id FROM announcements WHERE id=?{oc}", [ann_id] + op
        ).fetchone()
        if not row:
            abort(404)
        if not is_admin_like(g.user) and row["user_id"] != g.user["id"]:
            abort(403)
        conn.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    return redirect(url_for("announcements.index"))
