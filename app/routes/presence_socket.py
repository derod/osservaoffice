"""
presence_socket.py
Real-time presence tracking via a dedicated /presence Socket.IO namespace.

Architecture:
  - In-memory registry: _presence maps user_id -> {state, sid, org_id, name, initials, avatar_color}
  - One socket connection per browser tab; last writer wins per user_id
  - On connect  → mark user online, broadcast to org peers
  - On heartbeat → reset idle timeout, keep online
  - On idle      → client signals away; update state, broadcast
  - On disconnect → mark offline, persist last_seen_at to DB, broadcast
  - /api/presence/<org_id> → HTTP snapshot for non-real-time fallback

Org scoping:
  - super_admin receives presence for ALL users
  - regular users receive presence only for their own organization
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from flask import request
from flask_socketio import emit, join_room, leave_room
from app.auth_utils import get_current_user
from app.database import db_conn

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory registry
# ---------------------------------------------------------------------------

_lock = threading.Lock()

# user_id (int) -> dict
_presence: dict[int, dict] = {}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _initials(name: str) -> str:
    if not name:
        return "?"
    parts = name.strip().split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else parts[0][:2].upper()


def _room_for(org_id) -> str:
    """SocketIO room name for an org's presence feed. super_admin uses 'presence_all'."""
    if org_id is None:
        return "presence_all"
    return f"presence_org_{org_id}"


def _entry_payload(entry: dict) -> dict:
    """Serialize a presence entry for the wire."""
    return {
        "user_id":     entry["user_id"],
        "name":        entry["name"],
        "initials":    entry["initials"],
        "avatar_color": entry.get("avatar_color", "#6366f1"),
        "state":       entry["state"],        # "online" | "away" | "offline"
        "last_seen_at": entry.get("last_seen_at"),
        "org_id":      entry.get("org_id"),
    }


def get_presence_snapshot(org_id=None) -> list[dict]:
    """
    Return current presence list.
    org_id=None → all users (super_admin view).
    """
    with _lock:
        entries = list(_presence.values())
    if org_id is not None:
        entries = [e for e in entries if e.get("org_id") == org_id]
    return [_entry_payload(e) for e in entries]


def _persist_last_seen(user_id: int):
    """Write last_seen_at to the database (called on disconnect only)."""
    now = _now_utc()
    try:
        with db_conn() as conn:
            conn.execute(
                "UPDATE users SET last_seen_at=? WHERE id=?",
                (now, user_id),
            )
    except Exception:
        log.exception("Failed to persist last_seen_at for user %s", user_id)


# ---------------------------------------------------------------------------
# Socket event registration
# ---------------------------------------------------------------------------

def register_presence_events(socketio):
    """Attach presence events to the /presence namespace."""

    @socketio.on("connect", namespace="/presence")
    def on_connect():
        user = get_current_user()
        if not user:
            return False  # reject unauthenticated

        uid = user["id"]
        org_id = user.get("organization_id")  # None for super_admin
        sid = request.sid

        entry = {
            "user_id":     uid,
            "sid":         sid,
            "name":        user.get("full_name", ""),
            "initials":    _initials(user.get("full_name", "")),
            "avatar_color": user.get("avatar_color", "#6366f1"),
            "state":       "online",
            "last_seen_at": _now_utc(),
            "org_id":      org_id,
        }

        with _lock:
            _presence[uid] = entry

        # Join the org room so we can broadcast to peers
        join_room(_room_for(org_id))
        # super_admin always joins the all-room too
        if user.get("role") == "super_admin":
            join_room("presence_all")

        # Send current snapshot to the connecting client
        snapshot = get_presence_snapshot(org_id)
        emit("presence_snapshot", {"presence": snapshot})

        # Notify org peers that this user came online
        emit(
            "presence_update",
            {"user": _entry_payload(entry)},
            to=_room_for(org_id),
            skip_sid=sid,
        )

    @socketio.on("disconnect", namespace="/presence")
    def on_disconnect():
        sid = request.sid
        user_id = None

        with _lock:
            for uid, entry in list(_presence.items()):
                if entry.get("sid") == sid:
                    user_id = uid
                    org_id = entry.get("org_id")
                    entry["state"] = "offline"
                    entry["last_seen_at"] = _now_utc()
                    offline_payload = _entry_payload(entry)
                    del _presence[uid]
                    break
            else:
                return  # sid not tracked

        leave_room(_room_for(org_id))

        # Persist to DB
        _persist_last_seen(user_id)

        # Notify peers
        emit(
            "presence_update",
            {"user": offline_payload},
            to=_room_for(org_id),
        )

    @socketio.on("presence_heartbeat", namespace="/presence")
    def on_heartbeat():
        """Client pings every 30 s to stay online."""
        sid = request.sid
        with _lock:
            for entry in _presence.values():
                if entry.get("sid") == sid:
                    entry["state"] = "online"
                    entry["last_seen_at"] = _now_utc()
                    break

    @socketio.on("presence_idle", namespace="/presence")
    def on_idle():
        """Client signals the user has been idle (no mouse/key activity)."""
        sid = request.sid
        updated = None
        org_id = None
        with _lock:
            for entry in _presence.values():
                if entry.get("sid") == sid:
                    entry["state"] = "away"
                    entry["last_seen_at"] = _now_utc()
                    updated = _entry_payload(entry)
                    org_id = entry.get("org_id")
                    break
        if updated:
            emit(
                "presence_update",
                {"user": updated},
                to=_room_for(org_id),
            )

    @socketio.on("presence_active", namespace="/presence")
    def on_active():
        """Client signals the user returned from idle."""
        sid = request.sid
        updated = None
        org_id = None
        with _lock:
            for entry in _presence.values():
                if entry.get("sid") == sid:
                    entry["state"] = "online"
                    entry["last_seen_at"] = _now_utc()
                    updated = _entry_payload(entry)
                    org_id = entry.get("org_id")
                    break
        if updated:
            emit(
                "presence_update",
                {"user": updated},
                to=_room_for(org_id),
            )
