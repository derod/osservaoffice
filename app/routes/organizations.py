"""
organizations.py — super_admin-only platform control center.

Routes:
  /admin/platform                  — platform overview dashboard
  /admin/organizations             — organizations list
  /admin/organizations/new         — create org
  /admin/organizations/<id>/edit   — edit org
  /admin/organizations/<id>/toggle — activate / suspend (POST)
  /admin/leads                     — lead pipeline list
  /admin/leads/<id>                — lead detail + full update
  /admin/leads/<id>/convert        — quick-convert to org (POST)
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, g, abort, flash
from app.auth_utils import super_admin_required
from app.database import db_conn

bp = Blueprint("organizations", __name__, url_prefix="/admin")
log = logging.getLogger(__name__)


# ─── Pipeline config ─────────────────────────────────────────────────────────

_PIPELINE_STAGES = [
    "new",
    "contacted",
    "demo_scheduled",
    "qualified",
    "proposal_sent",
    "onboarding",
    "closed_won",
    "closed_lost",
    "archived",
]

# Stages considered "active" prospects (not closed/archived)
_ACTIVE_STAGES = {"new", "contacted", "demo_scheduled", "qualified", "proposal_sent", "onboarding"}

# Stages that represent conversion-ready leads
_CONVERSION_STAGES = {"qualified", "proposal_sent", "onboarding"}

_STAGE_LABELS = {
    "new":            "New",
    "contacted":      "Contacted",
    "demo_scheduled": "Demo Scheduled",
    "qualified":      "Qualified",
    "proposal_sent":  "Proposal Sent",
    "onboarding":     "Onboarding",
    "closed_won":     "Closed Won",
    "closed_lost":    "Closed Lost",
    "archived":       "Archived",
}

_SOURCES = [
    "website",
    "referral",
    "linkedin",
    "email_campaign",
    "conference",
    "direct",
    "other",
]

_SOURCE_LABELS = {
    "website":         "Website",
    "referral":        "Referral",
    "linkedin":        "LinkedIn",
    "email_campaign":  "Email Campaign",
    "conference":      "Conference / Event",
    "direct":          "Direct Contact",
    "other":           "Other",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ─── Platform dashboard ─────────────────────────────────────────────────────

@bp.route("/platform")
@super_admin_required
def platform_dashboard():
    with db_conn() as conn:
        total_orgs = conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0]
        active_orgs = conn.execute(
            "SELECT COUNT(*) FROM organizations WHERE is_active = 1 AND status = 'active'"
        ).fetchone()[0]
        trial_orgs = conn.execute(
            "SELECT COUNT(*) FROM organizations WHERE plan = 'trial' AND is_active = 1"
        ).fetchone()[0]
        suspended_orgs = conn.execute(
            "SELECT COUNT(*) FROM organizations WHERE status = 'suspended' OR is_active = 0"
        ).fetchone()[0]
        total_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role != 'super_admin'"
        ).fetchone()[0]

        # Recent leads (last 10)
        recent_leads = [dict(r) for r in conn.execute(
            "SELECT * FROM demo_requests ORDER BY created_at DESC LIMIT 10"
        ).fetchall()]

        # Lead metrics
        new_leads_count = conn.execute(
            "SELECT COUNT(*) FROM demo_requests WHERE pipeline_stage = 'new'"
        ).fetchone()[0]

        this_month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        leads_this_month = conn.execute(
            "SELECT COUNT(*) FROM demo_requests WHERE created_at >= ?",
            (this_month_start,)
        ).fetchone()[0]

        conversion_ready = conn.execute(
            "SELECT COUNT(*) FROM demo_requests WHERE pipeline_stage IN ('qualified','proposal_sent','onboarding')"
        ).fetchone()[0]

        # Recent organizations
        recent_orgs = [dict(r) for r in conn.execute("""
            SELECT o.*, COUNT(u.id) AS user_count
            FROM organizations o
            LEFT JOIN users u ON u.organization_id = o.id
            GROUP BY o.id
            ORDER BY o.created_at DESC
            LIMIT 5
        """).fetchall()]

        # Stage breakdown for mini chart
        stage_counts = {}
        for s in _PIPELINE_STAGES:
            stage_counts[s] = conn.execute(
                "SELECT COUNT(*) FROM demo_requests WHERE pipeline_stage=?", (s,)
            ).fetchone()[0]

    return render_template("admin/platform.html",
        current_user=g.user,
        total_orgs=total_orgs,
        active_orgs=active_orgs,
        trial_orgs=trial_orgs,
        suspended_orgs=suspended_orgs,
        total_users=total_users,
        recent_leads=recent_leads,
        new_leads_count=new_leads_count,
        leads_this_month=leads_this_month,
        conversion_ready=conversion_ready,
        recent_orgs=recent_orgs,
        stage_counts=stage_counts,
        stage_labels=_STAGE_LABELS,
    )


# ─── Organizations list ──────────────────────────────────────────────────────

@bp.route("/organizations")
@super_admin_required
def list_orgs():
    with db_conn() as conn:
        orgs = [dict(r) for r in conn.execute(
            "SELECT * FROM organizations ORDER BY name"
        ).fetchall()]
        for org in orgs:
            org["user_count"] = conn.execute(
                "SELECT COUNT(*) FROM users WHERE organization_id=?", (org["id"],)
            ).fetchone()[0]
            org["case_count"] = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE organization_id=?", (org["id"],)
            ).fetchone()[0]
    return render_template("admin/organizations.html",
        current_user=g.user, organizations=orgs)


@bp.route("/organizations/new", methods=["GET", "POST"])
@super_admin_required
def new_org():
    prefill = request.args  # allow pre-fill from lead conversion
    error = None
    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip()
        slug = f.get("slug", "").strip().lower() or None
        plan = f.get("plan", "trial")
        status = f.get("status", "active")
        is_active = 1 if f.get("is_active") == "on" else 0
        trial_ends_at = f.get("trial_ends_at") or None
        lead_id = f.get("lead_id") or None

        if not name:
            error = "Organization name is required."
        else:
            with db_conn() as conn:
                try:
                    conn.execute("""
                        INSERT INTO organizations
                            (name, slug, plan, status, is_active, trial_ends_at)
                        VALUES (?,?,?,?,?,?)
                    """, (name, slug, plan, status, is_active, trial_ends_at))
                    # If converting from a lead, advance its stage
                    if lead_id:
                        conn.execute("""
                            UPDATE demo_requests
                            SET pipeline_stage='closed_won',
                                conversion_notes=COALESCE(conversion_notes||char(10)||'Organization created.',
                                                          'Organization created.'),
                                updated_at=?
                            WHERE id=?
                        """, (_now_utc(), lead_id))
                        flash("Organization created and lead marked as Closed Won.", "success")
                    return redirect(url_for("organizations.list_orgs"))
                except Exception as e:
                    if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                        error = "Slug already in use. Choose a different one."
                    else:
                        raise

    return render_template("admin/org_form.html",
        current_user=g.user, org=None, error=error, prefill=prefill)


@bp.route("/organizations/<int:org_id>/edit", methods=["GET", "POST"])
@super_admin_required
def edit_org(org_id):
    with db_conn() as conn:
        org = conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        abort(404)
    org = dict(org)

    error = None
    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip()
        slug = f.get("slug", "").strip().lower() or None
        plan = f.get("plan", "trial")
        status = f.get("status", "active")
        is_active = 1 if f.get("is_active") == "on" else 0
        trial_ends_at = f.get("trial_ends_at") or None

        if not name:
            error = "Organization name is required."
        else:
            with db_conn() as conn:
                try:
                    conn.execute("""
                        UPDATE organizations
                        SET name=?, slug=?, plan=?, status=?, is_active=?,
                            trial_ends_at=?, updated_at=datetime('now')
                        WHERE id=?
                    """, (name, slug, plan, status, is_active, trial_ends_at, org_id))
                    return redirect(url_for("organizations.list_orgs"))
                except Exception as e:
                    if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                        error = "Slug already in use. Choose a different one."
                    else:
                        raise

    return render_template("admin/org_form.html",
        current_user=g.user, org=org, error=error, prefill={})


@bp.route("/organizations/<int:org_id>/toggle", methods=["POST"])
@super_admin_required
def toggle_org(org_id):
    with db_conn() as conn:
        org = conn.execute("SELECT id, is_active, status FROM organizations WHERE id=?", (org_id,)).fetchone()
        if not org:
            abort(404)
        if org["is_active"]:
            conn.execute(
                "UPDATE organizations SET is_active=0, status='suspended', updated_at=datetime('now') WHERE id=?",
                (org_id,)
            )
            flash("Organization suspended.", "success")
        else:
            conn.execute(
                "UPDATE organizations SET is_active=1, status='active', updated_at=datetime('now') WHERE id=?",
                (org_id,)
            )
            flash("Organization activated.", "success")
    return redirect(url_for("organizations.list_orgs"))


# ─── Leads pipeline ──────────────────────────────────────────────────────────

@bp.route("/leads")
@super_admin_required
def leads_list():
    stage_filter    = request.args.get("stage", "").strip()
    interest_filter = request.args.get("interest_type", "").strip()
    search          = request.args.get("q", "").strip()
    date_from       = request.args.get("date_from", "").strip()
    date_to         = request.args.get("date_to", "").strip()
    source_filter   = request.args.get("source", "").strip()

    q = "SELECT * FROM demo_requests WHERE 1=1"
    params = []

    if stage_filter and stage_filter in _PIPELINE_STAGES:
        q += " AND pipeline_stage = ?"
        params.append(stage_filter)
    if interest_filter:
        q += " AND interest_type = ?"
        params.append(interest_filter)
    if source_filter and source_filter in _SOURCES:
        q += " AND source = ?"
        params.append(source_filter)
    if search:
        q += " AND (email LIKE ? OR firm_name LIKE ? OR full_name LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if date_from:
        q += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        q += " AND created_at <= ?"
        params.append(date_to + " 23:59:59")

    q += " ORDER BY created_at DESC"

    with db_conn() as conn:
        leads = [dict(r) for r in conn.execute(q, params).fetchall()]

        # Stage counts for tabs
        stage_counts = {"all": conn.execute("SELECT COUNT(*) FROM demo_requests").fetchone()[0]}
        for s in _PIPELINE_STAGES:
            stage_counts[s] = conn.execute(
                "SELECT COUNT(*) FROM demo_requests WHERE pipeline_stage=?", (s,)
            ).fetchone()[0]

        # Interest types present
        interest_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT interest_type FROM demo_requests ORDER BY interest_type"
        ).fetchall()]

        # Reporting metrics
        this_month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        new_this_month = conn.execute(
            "SELECT COUNT(*) FROM demo_requests WHERE created_at >= ?",
            (this_month_start,)
        ).fetchone()[0]

        conversion_ready = conn.execute(
            "SELECT COUNT(*) FROM demo_requests WHERE pipeline_stage IN ('qualified','proposal_sent','onboarding')"
        ).fetchone()[0]

        # Interest type distribution
        interest_dist = [dict(r) for r in conn.execute("""
            SELECT interest_type, COUNT(*) as cnt
            FROM demo_requests
            GROUP BY interest_type
            ORDER BY cnt DESC
        """).fetchall()]

    return render_template("admin/leads.html",
        current_user=g.user,
        leads=leads,
        stage_counts=stage_counts,
        stage_labels=_STAGE_LABELS,
        stages=_PIPELINE_STAGES,
        interest_types=interest_types,
        sources=_SOURCES,
        source_labels=_SOURCE_LABELS,
        stage_filter=stage_filter,
        interest_filter=interest_filter,
        source_filter=source_filter,
        search=search,
        date_from=date_from,
        date_to=date_to,
        new_this_month=new_this_month,
        conversion_ready=conversion_ready,
        interest_dist=interest_dist,
    )


@bp.route("/leads/<int:lead_id>", methods=["GET", "POST"])
@super_admin_required
def lead_detail(lead_id):
    with db_conn() as conn:
        lead = conn.execute("SELECT * FROM demo_requests WHERE id=?", (lead_id,)).fetchone()
        if not lead:
            abort(404)
        lead = dict(lead)

        if request.method == "POST":
            f = request.form
            new_stage         = f.get("pipeline_stage", lead.get("pipeline_stage", "new")).strip()
            new_notes         = f.get("notes", "").strip() or None
            new_conversion    = f.get("conversion_notes", "").strip() or None
            assigned_to       = f.get("assigned_to_name", "").strip() or None
            follow_up         = f.get("follow_up_date", "").strip() or None

            if new_stage not in _PIPELINE_STAGES:
                new_stage = lead.get("pipeline_stage", "new")

            conn.execute("""
                UPDATE demo_requests
                SET pipeline_stage=?, notes=?, conversion_notes=?,
                    assigned_to_name=?, follow_up_date=?,
                    updated_at=?
                WHERE id=?
            """, (new_stage, new_notes, new_conversion, assigned_to, follow_up,
                  _now_utc(), lead_id))
            flash("Lead updated.", "success")
            return redirect(url_for("organizations.lead_detail", lead_id=lead_id))

    # Determine next recommended stage
    current_stage = lead.get("pipeline_stage") or "new"
    try:
        stage_idx = _PIPELINE_STAGES.index(current_stage)
        next_stage = _PIPELINE_STAGES[stage_idx + 1] if stage_idx < len(_PIPELINE_STAGES) - 1 else None
    except ValueError:
        next_stage = None

    is_conversion_ready = current_stage in _CONVERSION_STAGES

    return render_template("admin/lead_detail.html",
        current_user=g.user,
        lead=lead,
        stages=_PIPELINE_STAGES,
        stage_labels=_STAGE_LABELS,
        sources=_SOURCES,
        source_labels=_SOURCE_LABELS,
        next_stage=next_stage,
        is_conversion_ready=is_conversion_ready,
    )


@bp.route("/leads/<int:lead_id>/advance", methods=["POST"])
@super_admin_required
def advance_lead_stage(lead_id):
    """One-click advance to next pipeline stage."""
    with db_conn() as conn:
        lead = conn.execute(
            "SELECT id, pipeline_stage FROM demo_requests WHERE id=?", (lead_id,)
        ).fetchone()
        if not lead:
            abort(404)
        current = lead["pipeline_stage"] or "new"
        try:
            idx = _PIPELINE_STAGES.index(current)
            if idx < len(_PIPELINE_STAGES) - 1:
                new_stage = _PIPELINE_STAGES[idx + 1]
                conn.execute(
                    "UPDATE demo_requests SET pipeline_stage=?, updated_at=? WHERE id=?",
                    (new_stage, _now_utc(), lead_id)
                )
                flash(f"Lead moved to {_STAGE_LABELS.get(new_stage, new_stage)}.", "success")
        except ValueError:
            pass
    return redirect(url_for("organizations.lead_detail", lead_id=lead_id))
