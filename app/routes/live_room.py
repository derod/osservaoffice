import os
from flask import Blueprint, render_template, request, jsonify, g
from werkzeug.utils import secure_filename
from app.auth_utils import login_required

bp = Blueprint("live_room", __name__, url_prefix="/live-room")

_DEFAULT_UPLOAD_BASE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static", "uploads",
)
UPLOAD_FOLDER = os.path.join(
    os.environ.get("UPLOAD_DIR", _DEFAULT_UPLOAD_BASE),
    "live_room",
)
ALLOWED_EXTENSIONS = {"mp4"}
MAX_MP4_BYTES = 200 * 1024 * 1024  # 200 MB


def _allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@bp.route("")
@login_required
def index():
    return render_template("live_room/index.html", active_nav="live_room")


@bp.route("/upload-mp4", methods=["POST"])
@login_required
def upload_mp4():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed_file(f.filename):
        return jsonify({"error": "Only .mp4 files are allowed"}), 400

    # Check Content-Length header before reading to avoid loading oversized files into memory
    content_length = request.content_length
    if content_length and content_length > MAX_MP4_BYTES:
        return jsonify({"error": "File exceeds 200 MB limit"}), 413

    data = f.read()
    if len(data) > MAX_MP4_BYTES:
        return jsonify({"error": "File exceeds 200 MB limit"}), 413

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    safe_name = secure_filename(f.filename)
    # Prefix with user id to avoid collisions
    user_id = g.user["id"]
    saved_name = f"{user_id}_{safe_name}"
    dest = os.path.join(UPLOAD_FOLDER, saved_name)

    with open(dest, "wb") as out:
        out.write(data)

    # Return a URL relative to static root — never expose filesystem path
    url = f"/static/uploads/live_room/{saved_name}"
    return jsonify({"url": url, "filename": safe_name}), 200
