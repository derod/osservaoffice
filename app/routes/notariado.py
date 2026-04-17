from flask import Blueprint, render_template, g
from app.auth_utils import login_required

bp = Blueprint("notariado", __name__, url_prefix="/notariado")


@bp.route("")
@login_required
def index():
    modules = [
        {"key": "notarial_acts",      "icon": "fa-file-signature",   "label": "Notarial Acts",       "desc": "Notarial acts catalog"},
        {"key": "appearers",          "icon": "fa-user-check",       "label": "Appearers",           "desc": "Parties and identification"},
        {"key": "protocol",           "icon": "fa-book",             "label": "Protocol",            "desc": "Official protocol registry"},
        {"key": "signatures",         "icon": "fa-pen-nib",          "label": "Signatures",          "desc": "Signature collection"},
        {"key": "certified_copies",   "icon": "fa-copy",             "label": "Certified Copies",    "desc": "Issued certified copies"},
        {"key": "payments",           "icon": "fa-money-bill-wave",  "label": "Payments",            "desc": "Notarial fees and payments"},
    ]
    return render_template(
        "notariado/index.html",
        current_user=g.user,
        modules=modules,
    )
