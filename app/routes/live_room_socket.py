"""
live_room_socket.py
SocketIO event handlers for the Live Room feature.

Architecture:
  - One shared room key: ROOM_ID = "main_live_room"
  - In-memory participant registry keyed by socket sid
  - All media signaling (offer/answer/ICE) is relayed server-side
    so the server never inspects media content.
  - Phase 2: swap ROOM_ID for a per-room slug and persist
    participant state in Redis or DB.
"""

from flask import request
from flask_socketio import join_room, leave_room, emit
from app.auth_utils import get_current_user

ROOM_ID = "main_live_room"

# sid -> { id, name, initials, presenting, camera_on }
_participants: dict[str, dict] = {}


def _initials(name: str) -> str:
    if not name:
        return "?"
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


def _room_roster() -> list[dict]:
    return list(_participants.values())


def register_socket_events(socketio):
    """Attach all Live Room socket events to the given SocketIO instance."""

    # ── Connection / disconnection ─────────────────────────────

    @socketio.on("connect", namespace="/live")
    def on_connect():
        user = get_current_user()
        if not user:
            return False  # reject unauthenticated connections

        sid = request.sid
        _participants[sid] = {
            "sid": sid,
            "id": user["id"],
            "name": user["full_name"],
            "initials": _initials(user["full_name"]),
            "presenting": False,
            "camera_on": False,
        }
        join_room(ROOM_ID)

        # Tell the newcomer who is already here
        emit("room_roster", {"participants": _room_roster()})

        # Tell everyone else that this person joined
        emit(
            "participant_joined",
            {"participant": _participants[sid]},
            to=ROOM_ID,
            skip_sid=sid,
        )

    @socketio.on("disconnect", namespace="/live")
    def on_disconnect():
        sid = request.sid
        participant = _participants.pop(sid, None)
        if participant:
            leave_room(ROOM_ID)
            emit(
                "participant_left",
                {"sid": sid, "name": participant["name"]},
                to=ROOM_ID,
            )
            # If the presenter disconnected, clear presenting state
            if participant.get("presenting"):
                emit("presenter_cleared", {"sid": sid}, to=ROOM_ID)

    # ── Chat ───────────────────────────────────────────────────

    @socketio.on("send_chat_message", namespace="/live")
    def on_chat_message(data):
        sid = request.sid
        p = _participants.get(sid)
        if not p:
            return
        text = str(data.get("text", "")).strip()[:500]
        if not text:
            return
        emit(
            "chat_message",
            {"sid": sid, "name": p["name"], "text": text},
            to=ROOM_ID,
        )

    # ── Participant state ──────────────────────────────────────

    @socketio.on("participant_state_update", namespace="/live")
    def on_state_update(data):
        sid = request.sid
        p = _participants.get(sid)
        if not p:
            return
        if "camera_on" in data:
            p["camera_on"] = bool(data["camera_on"])
        if "presenting" in data:
            p["presenting"] = bool(data["presenting"])
        emit(
            "participant_updated",
            {"participant": dict(p)},
            to=ROOM_ID,
        )

    # ── Presenter control ──────────────────────────────────────

    @socketio.on("start_presenting", namespace="/live")
    def on_start_presenting(data):
        sid = request.sid
        p = _participants.get(sid)
        if not p:
            return
        # Clear any existing presenter
        for other in _participants.values():
            other["presenting"] = False
        p["presenting"] = True
        emit(
            "presenter_changed",
            {
                "presenter_sid": sid,
                "presenter_name": p["name"],
                "kind": data.get("kind", "screen"),  # "screen" | "mp4" | "youtube"
            },
            to=ROOM_ID,
        )

    @socketio.on("stop_presenting", namespace="/live")
    def on_stop_presenting():
        sid = request.sid
        p = _participants.get(sid)
        if not p:
            return
        p["presenting"] = False
        emit("presenter_cleared", {"sid": sid}, to=ROOM_ID)

    # ── WebRTC signaling relay ─────────────────────────────────
    # The server only relays payloads; it never reads SDP or ICE content.

    def _valid_relay_target(target_sid):
        """Return True only if target_sid is a currently connected participant."""
        return target_sid and target_sid in _participants

    @socketio.on("webrtc_offer", namespace="/live")
    def on_offer(data):
        """Relay an SDP offer to a specific peer."""
        target_sid = data.get("target_sid")
        if not _valid_relay_target(target_sid):
            return
        emit(
            "webrtc_offer",
            {
                "from_sid": request.sid,
                "sdp": data.get("sdp"),
            },
            to=target_sid,
        )

    @socketio.on("webrtc_answer", namespace="/live")
    def on_answer(data):
        """Relay an SDP answer back to the offerer."""
        target_sid = data.get("target_sid")
        if not _valid_relay_target(target_sid):
            return
        emit(
            "webrtc_answer",
            {
                "from_sid": request.sid,
                "sdp": data.get("sdp"),
            },
            to=target_sid,
        )

    @socketio.on("webrtc_ice_candidate", namespace="/live")
    def on_ice(data):
        """Relay an ICE candidate to a specific peer."""
        target_sid = data.get("target_sid")
        if not _valid_relay_target(target_sid):
            return
        emit(
            "webrtc_ice_candidate",
            {
                "from_sid": request.sid,
                "candidate": data.get("candidate"),
            },
            to=target_sid,
        )
