/* live_room.js — OSSERVA OFFICE Live Room  (Phase 2: real-time)
 *
 * Architecture
 * ────────────
 *  - SocketIO namespace  /live   handles presence, chat, signaling relay
 *  - WebRTC peer-mesh    one RTCPeerConnection per remote participant
 *  - Local media         camera / screen via browser APIs
 *  - Passive features    MP4 upload + YouTube embed remain fully functional
 *
 * Signaling flow (mesh)
 * ─────────────────────
 *  On participant_joined  → local node creates offer → sends webrtc_offer
 *  Remote receives offer  → creates answer → sends webrtc_answer
 *  ICE candidates         → relayed via webrtc_ice_candidate
 *
 * Phase 3 hook points marked  // TODO(p3)
 */

const LR = (() => {
  "use strict";

  // ── Read server-injected user context ──────────────────────
  const _ud = document.getElementById("lr-user-data");
  const ME = {
    id:       _ud ? _ud.dataset.userId       : "",
    name:     _ud ? _ud.dataset.userName     : "You",
    initials: _ud ? _ud.dataset.userInitials : "?",
  };

  // ── Local media state ──────────────────────────────────────
  let cameraStream = null;
  let screenStream = null;
  let currentPanel = "none";

  // ── WebRTC / signaling state ───────────────────────────────
  let socket = null;
  let mySid  = null;

  // sid -> RTCPeerConnection
  const peerConns = {};
  // sid -> { name, initials, camera_on, presenting }
  const peers     = {};

  // ICE server config — extend with TURN for production
  const ICE_CONFIG = {
    iceServers: [
      { urls: "stun:stun.l.google.com:19302" },
      { urls: "stun:stun1.l.google.com:19302" },
      // TODO(p3): add TURN credentials from env for NAT traversal
    ],
  };

  // ── SocketIO connection ────────────────────────────────────

  function _connectSocket() {
    socket = io("/live", { transports: ["websocket", "polling"] });

    socket.on("connect", () => {
      mySid = socket.id;
      const selfTile = document.getElementById("tile-self");
      if (selfTile) selfTile.dataset.sid = mySid;
    });

    socket.on("disconnect", () => {
      mySid = null;
      // Clean up all peer connections
      Object.keys(peerConns).forEach(_closePeer);
    });

    // ── Presence ───────────────────────────────────────────

    // Received on connect — full current roster
    socket.on("room_roster", ({ participants }) => {
      participants.forEach(p => {
        if (p.sid === mySid) return;
        peers[p.sid] = p;
        _renderTile(p.sid);
        _createOffer(p.sid);
      });
      _updateCount();
    });

    socket.on("participant_joined", ({ participant }) => {
      if (participant.sid === mySid) return;
      peers[participant.sid] = participant;
      _renderTile(participant.sid);
      _updateCount();
      // The newcomer will send us an offer; we just wait
    });

    socket.on("participant_left", ({ sid }) => {
      _closePeer(sid);
      _removeTile(sid);
      delete peers[sid];
      _updateCount();
    });

    socket.on("participant_updated", ({ participant }) => {
      if (participant.sid === mySid) return;
      peers[participant.sid] = { ...peers[participant.sid], ...participant };
      _refreshTileMeta(participant.sid);
    });

    // ── Chat ───────────────────────────────────────────────

    socket.on("chat_message", ({ sid, name, text }) => {
      appendChatMessage({ sender: name, text, self: sid === mySid });
    });

    // ── Presenter ──────────────────────────────────────────

    socket.on("presenter_changed", ({ presenter_sid, presenter_name, kind }) => {
      // Mark presenting badge on the right tile
      document.querySelectorAll(".lr-presenting-badge").forEach(b => {
        b.style.display = "none";
      });
      const tile = document.querySelector(`[data-sid="${presenter_sid}"]`);
      if (tile) {
        const badge = tile.querySelector(".lr-presenting-badge");
        if (badge) badge.style.display = "flex";
      }
      // If someone else is screen-sharing, switch local panel to screen tab
      if (kind === "screen" && presenter_sid !== mySid) {
        // Remote screen shown via their video track in the main panel
        switchPanel("screen", document.querySelector('[data-panel="screen"]'));
      }
    });

    socket.on("presenter_cleared", ({ sid }) => {
      document.querySelectorAll(".lr-presenting-badge").forEach(b => {
        b.style.display = "none";
      });
      // If we were viewing remote screen, go back to none
      if (sid && sid !== mySid && currentPanel === "screen") {
        const screenVideo = document.getElementById("screen-video");
        if (!screenStream) {
          // No local screen share active; revert to empty
          screenVideo.srcObject = null;
          screenVideo.style.display = "none";
          document.getElementById("screen-empty").style.display = "flex";
          switchPanel("none", document.querySelector('[data-panel="none"]'));
        }
      }
    });

    // ── WebRTC signaling ───────────────────────────────────

    socket.on("webrtc_offer", async ({ from_sid, sdp }) => {
      await _handleOffer(from_sid, sdp);
    });

    socket.on("webrtc_answer", async ({ from_sid, sdp }) => {
      const pc = peerConns[from_sid];
      if (!pc) return;
      try {
        await pc.setRemoteDescription(sdp);
      } catch (e) {
        console.warn("[LR] setRemoteDescription (answer) failed", e);
      }
    });

    socket.on("webrtc_ice_candidate", async ({ from_sid, candidate }) => {
      const pc = peerConns[from_sid];
      if (!pc || !candidate) return;
      try {
        await pc.addIceCandidate(candidate);
      } catch (e) {
        // Silently ignore — stale candidates are normal
      }
    });
  }

  // ── WebRTC peer management ─────────────────────────────────

  function _buildPeerConnection(remoteSid) {
    if (peerConns[remoteSid]) return peerConns[remoteSid];

    const pc = new RTCPeerConnection(ICE_CONFIG);
    peerConns[remoteSid] = pc;

    // Send ICE candidates as they trickle in
    pc.onicecandidate = ({ candidate }) => {
      if (candidate) {
        socket.emit("webrtc_ice_candidate", {
          target_sid: remoteSid,
          candidate: candidate.toJSON(),
        });
      }
    };

    // Receive remote tracks
    pc.ontrack = (event) => {
      const stream = event.streams[0];
      if (!stream) return;

      // Determine track type by checking the stream id or track kind
      const track = event.track;
      if (track.kind === "video") {
        // Heuristic: if the peer is presenting, route to main panel; else tile
        const peerData = peers[remoteSid];
        if (peerData && peerData.presenting) {
          _attachToMainPanel(stream, remoteSid);
        } else {
          _attachToTile(remoteSid, stream);
        }
      }
    };

    // Add any local tracks we already have
    _addLocalTracksToPeer(pc);

    return pc;
  }

  function _addLocalTracksToPeer(pc) {
    const senders = pc.getSenders();
    const addIfNew = (track, stream) => {
      const already = senders.find(s => s.track && s.track.id === track.id);
      if (!already) pc.addTrack(track, stream);
    };
    if (cameraStream) cameraStream.getTracks().forEach(t => addIfNew(t, cameraStream));
    if (screenStream) screenStream.getTracks().forEach(t => addIfNew(t, screenStream));
  }

  async function _createOffer(remoteSid) {
    const pc = _buildPeerConnection(remoteSid);
    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      socket.emit("webrtc_offer", {
        target_sid: remoteSid,
        sdp: pc.localDescription,
      });
    } catch (e) {
      console.warn("[LR] createOffer failed", e);
    }
  }

  async function _handleOffer(fromSid, sdp) {
    const pc = _buildPeerConnection(fromSid);
    try {
      await pc.setRemoteDescription(sdp);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      socket.emit("webrtc_answer", {
        target_sid: fromSid,
        sdp: pc.localDescription,
      });
    } catch (e) {
      console.warn("[LR] handleOffer failed", e);
    }
  }

  function _closePeer(sid) {
    const pc = peerConns[sid];
    if (pc) {
      pc.close();
      delete peerConns[sid];
    }
  }

  // When a new local track is added (camera/screen), renegotiate all peers
  async function _renegotiateAll() {
    for (const remoteSid of Object.keys(peerConns)) {
      const pc = peerConns[remoteSid];
      _addLocalTracksToPeer(pc);
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        socket.emit("webrtc_offer", {
          target_sid: remoteSid,
          sdp: pc.localDescription,
        });
      } catch (e) {
        console.warn("[LR] renegotiate failed", e);
      }
    }
  }

  // ── Tile rendering ─────────────────────────────────────────

  function _renderTile(sid) {
    const p = peers[sid];
    if (!p || document.querySelector(`[data-sid="${sid}"]`)) return;

    const grid = document.getElementById("participants-grid");
    const tile = document.createElement("div");
    tile.className = "lr-participant-tile";
    tile.dataset.sid = sid;
    tile.innerHTML = `
      <div class="lr-tile-video-wrap">
        <video class="lr-tile-video lr-remote-video" autoplay playsinline style="display:none"></video>
        <div class="lr-tile-avatar">${escapeHtml(p.initials)}</div>
        <span class="lr-presenting-badge" style="display:none">
          <i class="fa-solid fa-display"></i> Presenting
        </span>
      </div>
      <div class="lr-tile-info">
        <span class="lr-tile-name">${escapeHtml(p.name)}</span>
        <span class="lr-tile-status">Connected</span>
      </div>`;
    grid.appendChild(tile);
  }

  function _removeTile(sid) {
    const tile = document.querySelector(`[data-sid="${sid}"]`);
    if (!tile) return;
    // Release any active video stream before removing the element
    const video = tile.querySelector("video");
    if (video && video.srcObject) {
      video.srcObject.getTracks().forEach(t => t.stop());
      video.srcObject = null;
    }
    tile.remove();
  }

  function _refreshTileMeta(sid) {
    const p = peers[sid];
    if (!p) return;
    const tile = document.querySelector(`[data-sid="${sid}"]`);
    if (!tile) return;
    const statusEl = tile.querySelector(".lr-tile-status");
    if (statusEl) {
      statusEl.textContent = p.camera_on ? "Camera on" : "Connected";
    }
  }

  function _attachToTile(sid, stream) {
    const tile = document.querySelector(`[data-sid="${sid}"]`);
    if (!tile) return;
    const video = tile.querySelector(".lr-remote-video");
    const avatar = tile.querySelector(".lr-tile-avatar");
    if (video) {
      video.srcObject = stream;
      video.style.display = "block";
      if (avatar) avatar.style.display = "none";
    }
  }

  function _attachToMainPanel(stream, fromSid) {
    // Show remote screen/video in the screen panel
    const video = document.getElementById("screen-video");
    const empty = document.getElementById("screen-empty");
    if (video) {
      video.srcObject = stream;
      video.style.display = "block";
      if (empty) empty.style.display = "none";
    }
    switchPanel("screen", document.querySelector('[data-panel="screen"]'));
  }

  function _updateCount() {
    const el = document.getElementById("participant-count");
    if (el) el.textContent = 1 + Object.keys(peers).length;
  }

  // ── Panel switching ────────────────────────────────────────

  function switchPanel(name, tabEl) {
    document.querySelectorAll(".lr-panel").forEach(p => p.classList.remove("lr-panel-active"));
    document.querySelectorAll(".lr-tab").forEach(t => t.classList.remove("active"));

    const panel = document.getElementById("panel-" + name);
    if (panel) panel.classList.add("lr-panel-active");
    if (tabEl) tabEl.classList.add("active");

    currentPanel = name;
  }

  // ── Camera ─────────────────────────────────────────────────

  async function toggleCamera() {
    const btn    = document.getElementById("btn-camera");
    const video  = document.getElementById("camera-video");
    const avatar = document.getElementById("camera-avatar");
    const status = document.getElementById("camera-status");

    if (cameraStream) {
      cameraStream.getTracks().forEach(t => t.stop());
      cameraStream = null;
      video.srcObject = null;
      video.style.display = "none";
      avatar.style.display = "flex";
      status.textContent = "Camera off";
      btn.classList.remove("lr-btn-active");
      btn.querySelector("span").textContent = "Start Camera";
      _emitStateUpdate({ camera_on: false });
      return;
    }

    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      video.srcObject = cameraStream;
      video.style.display = "block";
      avatar.style.display = "none";
      status.textContent = "Camera on";
      btn.classList.add("lr-btn-active");
      btn.querySelector("span").textContent = "Stop Camera";
      _emitStateUpdate({ camera_on: true });
      await _renegotiateAll();
    } catch (err) {
      showToast("Camera access denied or unavailable.", 3000);
    }
  }

  // ── Screen share ───────────────────────────────────────────

  async function toggleScreen() {
    const btn   = document.getElementById("btn-screen");
    const video = document.getElementById("screen-video");
    const empty = document.getElementById("screen-empty");

    if (screenStream) {
      screenStream.getTracks().forEach(t => t.stop());
      screenStream = null;
      video.srcObject = null;
      video.style.display = "none";
      empty.style.display = "flex";
      btn.classList.remove("lr-btn-active");
      btn.querySelector("span").textContent = "Share Screen";
      _emitStateUpdate({ presenting: false });
      if (socket) socket.emit("stop_presenting");
      return;
    }

    try {
      screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      video.srcObject = screenStream;
      video.style.display = "block";
      empty.style.display = "none";
      btn.classList.add("lr-btn-active");
      btn.querySelector("span").textContent = "Stop Sharing";
      switchPanel("screen", document.querySelector('[data-panel="screen"]'));

      // Mark self tile as presenting
      const selfBadge = document.querySelector("#tile-self .lr-presenting-badge");
      if (selfBadge) selfBadge.style.display = "flex";

      _emitStateUpdate({ presenting: true });
      if (socket) socket.emit("start_presenting", { kind: "screen" });
      await _renegotiateAll();

      const videoTrack = screenStream.getVideoTracks()[0];
      if (videoTrack) {
        videoTrack.addEventListener("ended", () => { toggleScreen(); });
      }
    } catch (err) {
      if (err.name !== "NotAllowedError") {
        showToast("Screen sharing failed: " + err.message, 3000);
      }
    }
  }

  function _emitStateUpdate(delta) {
    if (socket) socket.emit("participant_state_update", delta);
  }

  // ── MP4 upload (unchanged from Phase 1) ───────────────────

  function openUploadDialog() {
    document.getElementById("mp4-file-input").click();
  }

  async function handleMp4File(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".mp4")) {
      showToast("Only .mp4 files are supported.", 3000);
      return;
    }
    if (file.size > 200 * 1024 * 1024) {
      showToast("File is too large. Maximum is 200 MB.", 3000);
      return;
    }

    const toast    = document.getElementById("upload-toast");
    const toastMsg = document.getElementById("upload-toast-msg");
    toastMsg.textContent = "Uploading…";
    toast.style.display = "flex";

    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch("/live-room/upload-mp4", { method: "POST", body: formData });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Upload failed");

      const videoEl = document.getElementById("mp4-video");
      const empty   = document.getElementById("mp4-empty");
      videoEl.src = data.url;
      videoEl.style.display = "block";
      empty.style.display = "none";

      switchPanel("mp4", document.querySelector('[data-panel="mp4"]'));
      if (socket) socket.emit("start_presenting", { kind: "mp4" });
      toastMsg.textContent = "Upload complete!";
      setTimeout(() => { toast.style.display = "none"; }, 1800);
    } catch (err) {
      toast.style.display = "none";
      showToast("Upload error: " + err.message, 4000);
    }
    event.target.value = "";
  }

  // ── YouTube embed (unchanged from Phase 1) ────────────────

  function openYouTubeDialog() {
    document.getElementById("youtube-dialog").style.display = "flex";
    document.getElementById("youtube-url-input").focus();
    document.getElementById("youtube-error").style.display = "none";
  }

  function closeYouTubeDialog(event) {
    if (event.target === document.getElementById("youtube-dialog")) {
      closeYouTubeDialogForced();
    }
  }

  function closeYouTubeDialogForced() {
    document.getElementById("youtube-dialog").style.display = "none";
  }

  function extractYouTubeId(url) {
    const patterns = [
      /[?&]v=([a-zA-Z0-9_-]{11})/,
      /youtu\.be\/([a-zA-Z0-9_-]{11})/,
      /\/embed\/([a-zA-Z0-9_-]{11})/,
      /\/shorts\/([a-zA-Z0-9_-]{11})/,
    ];
    for (const re of patterns) {
      const m = url.match(re);
      if (m) return m[1];
    }
    return null;
  }

  function loadYouTube() {
    const raw     = document.getElementById("youtube-url-input").value.trim();
    const videoId = extractYouTubeId(raw);

    if (!videoId) {
      document.getElementById("youtube-error").style.display = "block";
      return;
    }

    const iframe = document.getElementById("youtube-iframe");
    const wrap   = document.getElementById("youtube-frame-wrap");
    const empty  = document.getElementById("youtube-empty");

    iframe.src = `https://www.youtube.com/embed/${videoId}?rel=0`;
    wrap.style.display = "block";
    empty.style.display = "none";

    closeYouTubeDialogForced();
    switchPanel("youtube", document.querySelector('[data-panel="youtube"]'));
    if (socket) socket.emit("start_presenting", { kind: "youtube" });
  }

  // ── Chat ───────────────────────────────────────────────────

  function sendChatMessage() {
    const input = document.getElementById("chat-input");
    const text  = input.value.trim();
    if (!text) return;
    input.value = "";

    if (socket && socket.connected) {
      // Server will broadcast back to everyone including sender
      socket.emit("send_chat_message", { text });
    } else {
      // Offline fallback: show locally only
      appendChatMessage({ sender: ME.name, text, self: true });
    }
  }

  function appendChatMessage({ sender, text, self }) {
    const container = document.getElementById("chat-messages");
    const empty     = document.getElementById("chat-empty");
    if (empty) empty.style.display = "none";

    const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    const msg = document.createElement("div");
    msg.className = "lr-chat-msg" + (self ? " lr-chat-msg-self" : "");
    msg.innerHTML = `
      <div class="lr-chat-meta">
        <span class="lr-chat-sender">${escapeHtml(sender)}</span>
        <span class="lr-chat-time">${time}</span>
      </div>
      <div class="lr-chat-bubble">${escapeHtml(text)}</div>`;

    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
  }

  // ── Leave room ─────────────────────────────────────────────

  function leaveRoom() {
    if (cameraStream)  { cameraStream.getTracks().forEach(t => t.stop());  cameraStream = null; }
    if (screenStream)  { screenStream.getTracks().forEach(t => t.stop());  screenStream = null; }
    if (socket)        { socket.disconnect(); }
    Object.keys(peerConns).forEach(_closePeer);
    window.location.href = "/dashboard";
  }

  // ── Toast ──────────────────────────────────────────────────

  let _toastTimer = null;
  function showToast(msg, duration = 3000) {
    const toast    = document.getElementById("upload-toast");
    const toastMsg = document.getElementById("upload-toast-msg");
    toastMsg.textContent = msg;
    toast.style.display = "flex";
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { toast.style.display = "none"; }, duration);
  }

  // ── Utilities ──────────────────────────────────────────────

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ── Boot ───────────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", () => {
    _connectSocket();
  });

  // ── Public API ─────────────────────────────────────────────

  return {
    switchPanel,
    toggleCamera,
    toggleScreen,
    openUploadDialog,
    handleMp4File,
    openYouTubeDialog,
    closeYouTubeDialog,
    closeYouTubeDialogForced,
    loadYouTube,
    sendChatMessage,
    appendChatMessage,
    leaveRoom,
    showToast,
  };
})();
