import logging
from flask import Blueprint, render_template, request
from app.database import db_conn

bp = Blueprint("public", __name__)
log = logging.getLogger(__name__)

_VALID_INTEREST_TYPES = {
    "Request Demo",
    "Pricing",
    "Customization",
    "Data Transfer Consultation",
    "Deployment Support",
}

_VALID_TEAM_SIZES = {
    "1-5", "6-15", "16-30", "31-60", "60+",
}

_VALID_SOURCES = {
    "website", "referral", "linkedin", "email_campaign",
    "conference", "direct", "other",
}


@bp.route("/about")
def about():
    return render_template("public/about.html")


@bp.route("/terms")
def terms():
    return render_template("public/terms.html")


@bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    submitted = False
    form_error = None

    if request.method == "POST":
        f = request.form

        full_name  = f.get("full_name",       "").strip()
        firm_name  = f.get("firm_name",        "").strip()
        email      = f.get("email",            "").strip().lower()
        phone      = f.get("phone",            "").strip() or None
        country    = f.get("country",          "").strip() or None
        team_size  = f.get("team_size",        "").strip() or None
        interest   = f.get("interest_type",    "").strip()
        current_sw = f.get("current_software", "").strip() or None
        message    = f.get("message",          "").strip() or None
        # Source attribution: hidden field filled from ?src= query param
        source     = f.get("source", "website").strip().lower()
        if source not in _VALID_SOURCES:
            source = "website"

        if not full_name or not firm_name or not email:
            form_error = "Please complete all required fields."
        elif "@" not in email or "." not in email.split("@")[-1]:
            form_error = "Please enter a valid email address."
        elif interest not in _VALID_INTEREST_TYPES:
            form_error = "Please select a valid interest type."
        elif team_size and team_size not in _VALID_TEAM_SIZES:
            form_error = "Please select a valid team size."
        else:
            try:
                with db_conn() as conn:
                    conn.execute("""
                        INSERT INTO demo_requests
                            (full_name, firm_name, email, phone, country,
                             team_size, interest_type, current_software, message,
                             source, pipeline_stage)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                    """, (full_name, firm_name, email, phone, country,
                          team_size, interest, current_sw, message, source))
                log.info("Lead captured: %s <%s> — %s [src:%s]",
                         full_name, email, interest, source)
                submitted = True
            except Exception:
                log.exception("Failed to save demo request from %s", email)
                form_error = "There was a problem submitting your request. Please try again."

    # Pass ?src= hint to template for hidden field
    source_hint = request.args.get("src", "website").strip().lower()
    if source_hint not in _VALID_SOURCES:
        source_hint = "website"

    return render_template(
        "public/contact.html",
        submitted=submitted,
        form_error=form_error,
        interest_types=sorted(_VALID_INTEREST_TYPES),
        team_sizes=["1-5", "6-15", "16-30", "31-60", "60+"],
        source_hint=source_hint,
    )
