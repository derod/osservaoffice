"""Gmail API integration service for OSSERVA OFFICE."""
import os
import uuid
import base64
import logging
from datetime import datetime

from app.database import db_conn, get_integration_setting, set_integration_setting

log = logging.getLogger(__name__)

# Default credential paths — check project root first, fall back to Railway volume
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _resolve_default_path(filename, railway_fallback):
    """Return project-root path if the file exists there, else the Railway volume path."""
    local = os.path.join(_PROJECT_ROOT, filename)
    if os.path.exists(local):
        return local
    return railway_fallback

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(_PROJECT_ROOT, "app", "static", "uploads"))
GMAIL_UPLOAD_SUBDIR = "gmail"


def _credentials_path():
    env = os.environ.get("GMAIL_CREDENTIALS_PATH")
    if env:
        return env
    return _resolve_default_path("credentials.json", "/data/secrets/gmail_credentials.json")


def _token_path():
    env = os.environ.get("GMAIL_TOKEN_PATH")
    if env:
        return env
    return _resolve_default_path("token.json", "/data/secrets/gmail_token.json")


def gmail_is_configured():
    """Return True only if credentials file exists and can be loaded."""
    return os.path.exists(_credentials_path())


def gmail_token_exists():
    """Return True if a token file exists (user has completed OAuth)."""
    return os.path.exists(_token_path())


def get_gmail_service():
    """Load credentials/token and return an authenticated Gmail API client.

    Raises RuntimeError if credentials are missing or auth fails.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. "
            "Run: pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2"
        )

    creds_path = _credentials_path()
    token_path = _token_path()

    if not os.path.exists(creds_path):
        raise RuntimeError(f"Gmail credentials file not found at {creds_path}")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_dir = os.path.dirname(token_path)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(
                "Gmail token missing or expired. "
                "Run the OAuth flow to generate a token."
            )

    return build("gmail", "v1", credentials=creds)


def _get_header(headers, name):
    """Extract a header value from Gmail message headers list."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def extract_email_addresses(header_value):
    """Parse a header like 'Name <email>, Name2 <email2>' into a clean string."""
    if not header_value:
        return ""
    return header_value.strip()


def extract_plain_text_body(payload):
    """Recursively extract plain text body from Gmail message payload."""
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")

    # Simple text/plain part
    if mime_type == "text/plain" and "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Multipart: recurse into parts
    parts = payload.get("parts", [])
    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if part_mime.startswith("multipart/"):
            result = extract_plain_text_body(part)
            if result:
                return result

    # Fallback: try text/html if no plain text found
    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                # Strip HTML tags for a rough plain text version
                import re
                return re.sub(r"<[^>]+>", "", html).strip()

    return ""


def list_pdf_attachments(payload):
    """Return list of dicts with PDF attachment info from a message payload."""
    attachments = []
    if not payload:
        return attachments

    parts = payload.get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})

        if filename and (
            mime_type == "application/pdf"
            or filename.lower().endswith(".pdf")
        ):
            attachments.append({
                "filename": filename,
                "mime_type": mime_type,
                "attachment_id": body.get("attachmentId", ""),
                "size": body.get("size", 0),
            })

        # Recurse for nested multipart
        if part.get("parts"):
            attachments.extend(list_pdf_attachments(part))

    return attachments


def download_attachment(service, msg_id, attachment_id):
    """Download an attachment from Gmail and return raw bytes."""
    result = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()
    data = result.get("data", "")
    return base64.urlsafe_b64decode(data)


def save_attachment_file(file_bytes, original_filename):
    """Save attachment bytes to disk and return (stored_filename, file_path)."""
    ext = os.path.splitext(original_filename)[1].lower() or ".pdf"
    stored_name = uuid.uuid4().hex + ext
    dest_dir = os.path.join(UPLOAD_DIR, GMAIL_UPLOAD_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)
    file_path = os.path.join(dest_dir, stored_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return stored_name, file_path


def create_document_record(conn, attachment_info, file_path, stored_filename,
                           file_size, uploader_user_id, client_id=None, case_id=None):
    """Create a row in the documents table for a Gmail PDF attachment."""
    cur = conn.execute("""
        INSERT INTO documents (original_filename, stored_filename, file_path,
            mime_type, file_size, case_id, client_id, uploaded_by_user_id, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        attachment_info["filename"],
        stored_filename,
        file_path,
        "application/pdf",
        file_size,
        case_id,
        client_id,
        uploader_user_id,
        f"Imported from Gmail email attachment",
    ))
    return cur.lastrowid


def _extract_pdf_text_safe(file_path):
    """Try to extract text from a PDF; return empty string on any failure."""
    try:
        from app.utils.pdf_utils import extract_text
        return extract_text(file_path)
    except Exception as e:
        log.warning("PDF text extraction failed for %s: %s", file_path, e)
        return ""


def match_client_for_email(conn, from_email):
    """Try to match sender email to an existing client.

    Returns client dict or None.
    """
    if not from_email:
        return None

    # Exact match
    client = conn.execute(
        "SELECT * FROM clients WHERE email = ? AND is_active = 1",
        (from_email,)
    ).fetchone()
    if client:
        return dict(client)

    # Case-insensitive match
    client = conn.execute(
        "SELECT * FROM clients WHERE LOWER(email) = LOWER(?) AND is_active = 1",
        (from_email.strip(),)
    ).fetchone()
    if client:
        return dict(client)

    return None


def create_client_from_email(conn, from_name, from_email):
    """Create a new client from email sender info. Returns new client id.

    Will NOT create if a client with the same email already exists.
    """
    # Guard against duplicates
    existing = conn.execute(
        "SELECT id FROM clients WHERE LOWER(email) = LOWER(?)",
        (from_email.strip(),)
    ).fetchone()
    if existing:
        return existing["id"]

    cur = conn.execute("""
        INSERT INTO clients (full_name, email, notes, is_active)
        VALUES (?, ?, ?, 1)
    """, (
        from_name or from_email.split("@")[0],
        from_email.strip(),
        "Created from Gmail import",
    ))
    return cur.lastrowid


def link_message_to_existing_client(conn, gmail_msg_local_id, client_id):
    """Link a gmail_messages row to an existing client."""
    conn.execute("""
        UPDATE gmail_messages
        SET matched_client_id = ?, processed_status = 'matched_existing_client',
            last_synced_at = datetime('now')
        WHERE id = ?
    """, (client_id, gmail_msg_local_id))

    # Also update any documents created from this message's attachments
    gmail_row = conn.execute(
        "SELECT gmail_message_id FROM gmail_messages WHERE id = ?",
        (gmail_msg_local_id,)
    ).fetchone()
    if gmail_row:
        att_docs = conn.execute(
            "SELECT document_id FROM gmail_attachments WHERE gmail_message_id = ? AND document_id IS NOT NULL",
            (gmail_row["gmail_message_id"],)
        ).fetchall()
        for ad in att_docs:
            conn.execute(
                "UPDATE documents SET client_id = ? WHERE id = ?",
                (client_id, ad["document_id"])
            )


def upsert_gmail_message(conn, msg_data):
    """Insert or update a gmail message record. Returns local id.

    msg_data is a dict with keys matching gmail_messages columns.
    """
    existing = conn.execute(
        "SELECT id FROM gmail_messages WHERE gmail_message_id = ?",
        (msg_data["gmail_message_id"],)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE gmail_messages SET
                subject = ?, from_name = ?, from_email = ?, to_emails = ?,
                cc_emails = ?, snippet = ?, body_text = ?, received_at = ?,
                has_pdf = ?, last_synced_at = datetime('now')
            WHERE gmail_message_id = ?
        """, (
            msg_data.get("subject"), msg_data.get("from_name"),
            msg_data.get("from_email"), msg_data.get("to_emails"),
            msg_data.get("cc_emails"), msg_data.get("snippet"),
            msg_data.get("body_text"), msg_data.get("received_at"),
            msg_data.get("has_pdf", 0), msg_data["gmail_message_id"],
        ))
        return existing["id"]
    else:
        cur = conn.execute("""
            INSERT INTO gmail_messages (
                gmail_message_id, gmail_thread_id, subject, from_name, from_email,
                to_emails, cc_emails, snippet, body_text, received_at, has_pdf,
                processed_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
        """, (
            msg_data["gmail_message_id"], msg_data.get("gmail_thread_id"),
            msg_data.get("subject"), msg_data.get("from_name"),
            msg_data.get("from_email"), msg_data.get("to_emails"),
            msg_data.get("cc_emails"), msg_data.get("snippet"),
            msg_data.get("body_text"), msg_data.get("received_at"),
            msg_data.get("has_pdf", 0),
        ))
        return cur.lastrowid


def _parse_from_header(from_header):
    """Parse 'Name <email>' into (name, email)."""
    import re
    match = re.match(r'^"?(.+?)"?\s*<(.+?)>$', from_header.strip())
    if match:
        return match.group(1).strip().strip('"'), match.group(2).strip()
    # Bare email
    if "@" in from_header:
        return "", from_header.strip()
    return from_header.strip(), ""


def _parse_received_date(internal_date_ms):
    """Convert Gmail internalDate (ms since epoch) to datetime string."""
    try:
        ts = int(internal_date_ms) / 1000
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def sync_recent_gmail_messages(max_results=25, uploader_user_id=1):
    """Fetch recent inbox emails from Gmail, store metadata and PDF attachments.

    Returns dict with counts: {synced, new, errors, skipped}.
    """
    enabled = get_integration_setting("gmail_enabled")
    if enabled != "1":
        raise RuntimeError("Gmail integration is not enabled. Enable it in Settings.")

    service = get_gmail_service()

    # List recent messages
    results = service.users().messages().list(
        userId="me", labelIds=["INBOX"], maxResults=max_results
    ).execute()
    messages = results.get("messages", [])

    counts = {"synced": 0, "new": 0, "errors": 0, "skipped": 0}

    for msg_stub in messages:
        gmail_id = msg_stub["id"]

        try:
            with db_conn() as conn:
                # Skip if already imported
                existing = conn.execute(
                    "SELECT id FROM gmail_messages WHERE gmail_message_id = ?",
                    (gmail_id,)
                ).fetchone()
                if existing:
                    counts["skipped"] += 1
                    continue

            # Fetch full message
            msg = service.users().messages().get(
                userId="me", id=gmail_id, format="full"
            ).execute()

            headers = msg.get("payload", {}).get("headers", [])
            from_header = _get_header(headers, "From")
            from_name, from_email = _parse_from_header(from_header)

            payload = msg.get("payload", {})
            pdf_attachments = list_pdf_attachments(payload)

            msg_data = {
                "gmail_message_id": gmail_id,
                "gmail_thread_id": msg.get("threadId", ""),
                "subject": _get_header(headers, "Subject"),
                "from_name": from_name,
                "from_email": from_email,
                "to_emails": extract_email_addresses(_get_header(headers, "To")),
                "cc_emails": extract_email_addresses(_get_header(headers, "Cc")),
                "snippet": msg.get("snippet", ""),
                "body_text": extract_plain_text_body(payload),
                "received_at": _parse_received_date(msg.get("internalDate")),
                "has_pdf": 1 if pdf_attachments else 0,
            }

            with db_conn() as conn:
                local_id = upsert_gmail_message(conn, msg_data)

                # Try auto-matching client
                client = match_client_for_email(conn, from_email)
                if client:
                    conn.execute("""
                        UPDATE gmail_messages
                        SET matched_client_id = ?, processed_status = 'matched_existing_client'
                        WHERE id = ?
                    """, (client["id"], local_id))

                # Download PDF attachments
                for att in pdf_attachments:
                    att_id = att["attachment_id"]
                    if not att_id:
                        continue

                    # Check if attachment already stored
                    existing_att = conn.execute(
                        "SELECT id FROM gmail_attachments WHERE gmail_message_id = ? AND gmail_attachment_id = ?",
                        (gmail_id, att_id)
                    ).fetchone()
                    if existing_att:
                        continue

                    try:
                        file_bytes = download_attachment(service, gmail_id, att_id)
                        stored_name, file_path = save_attachment_file(file_bytes, att["filename"])
                        file_size = len(file_bytes)

                        # Create document record
                        doc_id = create_document_record(
                            conn, att, file_path, stored_name, file_size,
                            uploader_user_id,
                            client_id=client["id"] if client else None,
                        )

                        # Extract text (best effort)
                        extracted = _extract_pdf_text_safe(file_path)

                        conn.execute("""
                            INSERT INTO gmail_attachments (
                                gmail_message_id, gmail_attachment_id, filename,
                                mime_type, file_size, stored_filename, file_path,
                                is_pdf, extracted_text, document_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """, (
                            gmail_id, att_id, att["filename"],
                            att["mime_type"], file_size, stored_name,
                            file_path, extracted, doc_id,
                        ))
                    except Exception as e:
                        log.error("Failed to download attachment %s: %s", att["filename"], e)

            counts["new"] += 1
            counts["synced"] += 1

        except Exception as e:
            log.error("Failed to process Gmail message %s: %s", gmail_id, e)
            counts["errors"] += 1
            # Try to record the error
            try:
                with db_conn() as conn:
                    existing = conn.execute(
                        "SELECT id FROM gmail_messages WHERE gmail_message_id = ?",
                        (gmail_id,)
                    ).fetchone()
                    if existing:
                        conn.execute("""
                            UPDATE gmail_messages SET processed_status = 'error',
                                error_message = ? WHERE id = ?
                        """, (str(e)[:500], existing["id"]))
            except Exception:
                pass

    # Update last sync time
    try:
        set_integration_setting("gmail_last_sync", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass

    return counts
