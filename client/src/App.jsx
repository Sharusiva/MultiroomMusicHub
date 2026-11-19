import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MotionConfig } from "motion/react";
import * as Popover from "@radix-ui/react-popover";
import { ChevronDown, Copy, LogOut, QrCode } from "lucide-react";
import { ClockSync } from "./clock";
import { SyncPlayer } from "./syncPlayer";
import { api, createSocket, getToken, onAuthChange, setToken } from "./net";
import { coverColor } from "./lib/coverColor";
import Transport from "./views/Transport";
import Stage from "./views/Stage";
import Queue from "./views/Queue";
import ZoneDrawer, { groupRooms, zoneName } from "./views/ZoneDrawer";
import { syncHealth } from "./views/SignalPath";
import { AuthScreen, Grille, Home, formatCode } from "./views/Lobby";
import ClusterView from "./ClusterView";
import Invite from "./Invite";

const I = { strokeWidth: 1.5, "aria-hidden": true };

function deviceKind() {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android phone"
    : /Macintosh/.test(ua) ? "Mac" : /Windows/.test(ua) ? "PC" : /Linux/.test(ua) ? "laptop" : "device";
}

// An invite link looks like http://<host>/?join=K7P2QX
function readInviteCode() {
  const code = new URLSearchParams(location.search).get("join");
  return code ? code.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6) : null;
}
function clearInviteCode() {
  history.replaceState(null, "", location.pathname);
}

/** The dashboard for the demo lives only at /cluster. Nothing in the app links to it. */
export default function App() {
  if (location.pathname.replace(/\/+$/, "") === "/cluster") {
    return (
      <div className="shell bare">
        <header className="topbar"><div className="brand"><Grille /><span>Multiroom cluster</span></div></header>
        <main className="main"><ClusterView /></main>
      </div>
    );
  }
  return <Player />;
}

function Player() {
  const [token, setTok] = useState(getToken);
  const [user, setUser] = useState(null);
  const [invite, setInvite] = useState(readInviteCode);
  const [conn, setConn] = useState({ connected: false, server: null });
  const [rooms, setRooms] = useState([]);
  const [roomsLoaded, setRoomsLoaded] = useState(false);
  const [roomId, setRoomId] = useState(null);
  const [zoneId, setZoneId] = useState(null);
  const [roomState, setRoomState] = useState(null);
  const [queue, setQueue] = useState([]);
  const [presence, setPresence] = useState(null);
  const [library, setLibrary] = useState([]);
  const [info, setInfo] = useState({});
  const [zonesOpen, setZonesOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [, setTick] = useState(0);

  const core = useMemo(() => {
    const clock = new ClockSync();
    const c = { clock, player: new SyncPlayer(clock), socket: null };
    window.mmh = c; // in the browser console during the demo: mmh.player.drift, mmh.clock.rtt
    return c;
  }, []);
  const roomRef = useRef(null);
  const zoneRef = useRef(null);
  const userRef = useRef(null);
  userRef.current = user;
  const localEdits = useRef({});
  const pendingVol = useRef({});
  const volTimer = useRef(null);

  const flash = useCallback((msg) => {
    setToast(msg);
    clearTimeout(flash.t);
    flash.t = setTimeout(() => setToast(null), 3400);
  }, []);

  useEffect(() => onAuthChange(setTok), []);
  useEffect(() => { api("/info").then(setInfo).catch(() => {}); }, []);

  // who am I? (a saved token may have expired)
  useEffect(() => {
    if (!token) { setUser(null); return; }
    if (user) return;
    api("/auth/me").then((r) => setUser(r.user)).catch(() => setToken(null));
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadRooms = useCallback(() => api("/rooms").then((fresh) => {
    const now = Date.now();
    setRooms((prev) => fresh.map((r) => {
      const mine = prev.find((p) => p.id === r.id);
      return mine && now - (localEdits.current[r.id] || 0) < 1500 ? { ...r, volume: mine.volume } : r;
    }));
    setRoomsLoaded(true);
  }).catch(() => {}), []);
  const loadLibrary = useCallback(() => api("/tracks").then(setLibrary).catch(() => {}), []);

  useEffect(() => {
    if (!user) return;
    loadRooms();
    loadLibrary();
    const t = setInterval(loadRooms, 4000);
    return () => clearInterval(t);
  }, [user, loadRooms, loadLibrary]);

  useEffect(() => {
    if (!roomId) return;
    const t = setInterval(() => setTick((x) => x + 1), 250);
    return () => clearInterval(t);
  }, [roomId]);

  // Room-node status: tell the controller what this device is really doing
  // (playing / buffering / needs a tap, and its drift) every 2 s, and immediately
  // when that changes, so every device in the zone sees each speaker's health.
  useEffect(() => {
    if (!roomId) return;
    let lastState = null;
    const report = (force) => {
      const socket = core.socket;
      if (!socket?.connected || !roomRef.current) return;
      const st = core.player.status();
      if (!force && st.state === lastState && report.n++ % 4) return; // every 2 s, or on change
      lastState = st.state;
      socket.emit("status", { room_id: roomRef.current, ...st });
    };
    report.n = 0;
    const t = setInterval(() => report(false), 500);
    core.player.onStatus = () => report(true);
    report(true);
    return () => { clearInterval(t); core.player.onStatus = null; };
  }, [roomId, core]);

  const leaveToHome = useCallback((msg) => {
    core.socket?.emit("leave");
    roomRef.current = null;
    zoneRef.current = null;
    core.player.clear();
    setRoomId(null);
    setZoneId(null);
    setRoomState(null);
    setQueue([]);
    setPresence(null);
    setZonesOpen(false);
    if (msg) flash(msg);
  }, [core, flash]);

  const joinRoom = useCallback((id) => {
    const socket = core.socket;
    if (!socket || !id) return;
    core.player.unlock();
    roomRef.current = id;
    setRoomId(id);
    socket.emit("join", { room_id: id }, (resp) => {
      if (!resp || resp.error) {
        leaveToHome(resp?.error || "Could not open that room. Try again.");
        return;
      }
      if (zoneRef.current !== resp.zone_id) {
        core.player.clear();
        zoneRef.current = resp.zone_id;
      }
      setZoneId(resp.zone_id);
      setConn((c) => ({ ...c, server: resp.server }));
      core.player.setState(resp.state);
      setRoomState(resp.state);
      setQueue(resp.queue.items);
      setPresence(resp.presence);
    });
  }, [core, leaveToHome]);

  // One WebSocket per device, authenticated with the session token.
  useEffect(() => {
    if (!user || !token) return;
    const socket = createSocket({ token, device: deviceKind() });
    core.socket = socket;
    core.clock.attach(socket);
    core.player.onEnded = (s) =>
      socket.emit("command", { room_id: roomRef.current, action: "track_ended", version: s.version });

    socket.on("connect", () => {
      setConn((c) => ({ ...c, connected: true }));
      if (roomRef.current) joinRoom(roomRef.current); // after a node failure: re-join on the new node
    });
    socket.on("connect_error", (err) => { if (err?.message === "unauthorized") setToken(null); });
    socket.on("welcome", (w) => setConn({ connected: true, server: w.server }));
    socket.on("disconnect", () => setConn((c) => ({ ...c, connected: false })));
    socket.on("state", (s) => {
      if (s.room_id !== zoneRef.current) return;
      core.player.setState(s);
      setRoomState((prev) => (!prev || prev.room_id !== s.room_id || s.version >= prev.version ? s : prev));
    });
    socket.on("queue", (q) => q.room_id === zoneRef.current && setQueue(q.items));
    socket.on("presence", (p) => p.room_id === zoneRef.current && setPresence(p));
    socket.on("volumes", ({ volumes }) =>
      setRooms((rs) => rs.map((r) => (r.id in volumes ? { ...r, volume: volumes[r.id] } : r))));
    socket.on("regroup", ({ rooms: affected }) => {
      if (affected.includes(roomRef.current)) joinRoom(roomRef.current);
      loadRooms();
    });
    socket.on("library_changed", loadLibrary);
    // a song was renamed: update titles everywhere without touching playback
    socket.on("track_updated", (t) => {
      const patch = (tr) => (tr && tr.id === t.id ? { ...tr, title: t.title, artist: t.artist } : tr);
      setRoomState((s) => (s && s.track?.id === t.id ? { ...s, track: patch(s.track) } : s));
      setQueue((q) => q.map((i) => (i.track?.id === t.id ? { ...i, track: patch(i.track) } : i)));
      if (core.player.state?.track?.id === t.id) core.player.state.track = patch(core.player.state.track);
      loadLibrary();
      loadRooms();
    });
    socket.on("rooms_changed", loadRooms);
    socket.on("room_closed", ({ room_id, user_id }) => {
      if (room_id !== roomRef.current) return;
      if (user_id && user_id !== userRef.current?.id) return; // someone else left
      leaveToHome(user_id ? "You left the room." : "This room was deleted by its owner.");
      loadRooms();
    });
    return () => { socket.removeAllListeners(); socket.disconnect(); core.socket = null; };
  }, [user, token, core, joinRoom, loadLibrary, loadRooms, leaveToHome]);

  // an invite link (?join=CODE) joins the room as soon as you're logged in
  useEffect(() => {
    if (!user || !invite || !conn.connected) return;
    api("/rooms/join", { method: "POST", json: { code: invite } })
      .then((room) => { loadRooms(); joinRoom(room.id); flash(`Joined ${room.name}`); })
      .catch((e) => flash(e.message))
      .finally(() => { setInvite(null); clearInviteCode(); });
  }, [user, invite, conn.connected, joinRoom, loadRooms, flash]);

  const myRoom = rooms.find((r) => r.id === roomId);
  useEffect(() => {
    if (myRoom) core.player.setVolume((myRoom.volume ?? 70) / 100);
  }, [core, myRoom?.volume]); // eslint-disable-line react-hooks/exhaustive-deps

  const track = roomState?.track;
  useEffect(() => {
    let live = true;
    coverColor(track?.cover, track?.color).then((rgb) => {
      if (live && rgb) document.documentElement.style.setProperty("--cover-rgb", rgb.join(", "));
    });
    return () => { live = false; };
  }, [track?.cover, track?.color]);

  const send = useCallback((action, extra = {}) => {
    if (!core.socket || !roomRef.current) return;
    core.socket.emit("command", { room_id: roomRef.current, action, ...extra }, (resp) => {
      if (resp?.error) flash(resp.error);
    });
  }, [core, flash]);

  const flushVolumes = useCallback(() => {
    clearTimeout(volTimer.current);
    volTimer.current = null;
    const v = pendingVol.current;
    pendingVol.current = {};
    if (Object.keys(v).length) core.socket?.emit("set_volumes", { volumes: v });
  }, [core]);
  const setVolumes = useCallback((map, flush = false) => {
    const now = Date.now();
    Object.keys(map).forEach((id) => { localEdits.current[id] = now; });
    setRooms((rs) => rs.map((r) => (r.id in map ? { ...r, volume: map[r.id] } : r)));
    Object.assign(pendingVol.current, map);
    if (flush) flushVolumes();
    else if (!volTimer.current) volTimer.current = setTimeout(flushVolumes, 70);
  }, [flushVolumes]);

  const createRoom = useCallback(async (name) => {
    const room = await api("/rooms", { method: "POST", json: { name } });
    await loadRooms();
    joinRoom(room.id);
    setInviteOpen(true); // show the code right away, so it can be shared
  }, [loadRooms, joinRoom]);

  const joinByCode = useCallback(async (code) => {
    const room = await api("/rooms/join", { method: "POST", json: { code } });
    await loadRooms();
    joinRoom(room.id);
    flash(`Joined ${room.name}`);
  }, [loadRooms, joinRoom, flash]);

  const handlers = useMemo(() => ({
    onMove: (id) => joinRoom(id),
    onLink: (id) => api(`/rooms/${id}/link`, { method: "POST", json: { to: roomRef.current } })
      .then(loadRooms).catch((e) => flash(e.message)),
    onUnlink: (id) => api(`/rooms/${id}/unlink`, { method: "POST" }).then(loadRooms).catch((e) => flash(e.message)),
    onDelete: (id) => api(`/rooms/${id}`, { method: "DELETE" }).then(loadRooms).catch((e) => flash(e.message)),
    onLeave: (id) => api(`/rooms/${id}/leave`, { method: "POST" }).then(loadRooms).catch((e) => flash(e.message)),
    onVolume: (map) => setVolumes(map),
    onVolumeCommit: (map) => setVolumes(map, true),
  }), [joinRoom, loadRooms, flash, setVolumes]);

  // Assign music to another room from here: the server applies it to that room's
  // queue and every device in that room hears it, without anyone switching rooms.
  const sendToRoom = useCallback(async (t, room, play) => {
    try {
      await api(`/rooms/${room.id}/queue`, { method: "POST", json: { track_id: t.id, play } });
      flash(play ? `Now playing ${t.title} in ${room.name}` : `Added ${t.title} to ${room.name}`);
      loadRooms();
    } catch (e) { flash(e.message); }
  }, [flash, loadRooms]);

  const deleteTrack = useCallback(async (t) => {
    try {
      const r = await api(`/tracks/${t.id}`, { method: "DELETE" });
      flash(r.removed_from_rooms ? `Deleted ${t.title} (removed from ${r.removed_from_rooms} room${r.removed_from_rooms === 1 ? "" : "s"})` : `Deleted ${t.title}`);
      loadLibrary();
    } catch (e) { flash(e.message); }
  }, [flash, loadLibrary]);

  const editTrack = useCallback(async (t, details) => {
    try {
      await api(`/tracks/${t.id}`, { method: "PATCH", json: details });
      flash(`Saved ${details.title}`);
    } catch (e) { flash(e.message); }
  }, [flash]);

  const resetCode = useCallback(async () => {
    try {
      await api(`/rooms/${roomRef.current}/code`, { method: "POST" });
      await loadRooms();
      flash("New code made. The old one no longer works.");
    } catch (e) { flash(e.message); }
  }, [loadRooms, flash]);

  const upload = async (e) => {
    const files = [...(e.target.files || [])];
    if (!files.length) return;
    setUploading(true);
    try {
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        const t = await api("/tracks", { method: "POST", body: fd });
        send("queue_add", { track_id: t.id });
      }
      flash(files.length === 1 ? "Uploaded and added to Up next" : `Uploaded ${files.length} songs`);
      loadLibrary();
    } catch (err) {
      flash(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const logout = useCallback(async () => {
    leaveToHome();
    try { await api("/auth/logout", { method: "POST" }); } catch { /* already gone */ }
    setToken(null);
    setUser(null);
    setRooms([]);
    setRoomsLoaded(false);
  }, [leaveToHome]);

  const playing = !!roomState?.is_playing;
  const togglePlay = useCallback(() => {
    if (core.player.blocked) {
      // Browser blocked autoplay. This tap only turns sound on for THIS device;
      // it must not pause the room for everyone else.
      core.player.blocked = false;
      core.player.apply();
      if (playing) return;
    }
    send(playing ? "pause" : "play");
  }, [core, playing, send]);

  // Safari/iOS block audio a page starts on its own (e.g. a song sent from another
  // room). Any tap or key press anywhere on the page counts, so turn sound on then.
  useEffect(() => {
    const wake = () => {
      if (!core.player.blocked) return;
      core.player.blocked = false;
      core.player.apply();
    };
    window.addEventListener("pointerdown", wake, true);
    window.addEventListener("keydown", wake, true);
    return () => {
      window.removeEventListener("pointerdown", wake, true);
      window.removeEventListener("keydown", wake, true);
    };
  }, [core]);

  useEffect(() => {
    if (!roomId) return;
    const onKey = (e) => {
      if (e.code !== "Space" || e.repeat) return;
      const el = document.activeElement;
      if (["INPUT", "TEXTAREA", "BUTTON", "SELECT"].includes(el?.tagName) || el?.getAttribute("role") === "slider") return;
      e.preventDefault();
      togglePlay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [roomId, togglePlay]);

  if (!token || !user) {
    if (token && !user) return <div className="join"><p className="muted">Signing you in…</p></div>;
    return <AuthScreen inviteCode={invite} onAuthed={(u) => { core.player.unlock(); setUser(u); }} />;
  }

  if (!roomId) {
    return (
      <>
        <Home user={user} rooms={rooms} loaded={roomsLoaded} onOpen={joinRoom} onCreate={createRoom}
          onJoin={joinByCode} onLogout={logout} />
        {toast && <div className="toast" role="status" style={{ bottom: 24 }}>{toast}</div>}
      </>
    );
  }

  const groups = groupRooms(rooms, zoneId);
  const myGroup = groups.find((g) => g.leader === zoneId);
  const zoneLabel = zoneName(myGroup) || myRoom?.name || "";
  const linked = (myGroup?.rooms.length || 0) > 1;
  const otherRooms = rooms.filter((r) => r.id !== zoneId && r.group_leader !== zoneId);
  const position = core.player.target() ?? 0;
  const waiting = playing && roomState && roomState.anchor_ms > core.clock.now();
  const health = syncHealth({ playing, waiting, blocked: core.player.blocked, driftMs: core.player.drift * 1000 });
  const isOwner = myRoom?.role === "owner";

  return (
    <MotionConfig reducedMotion="user">
      <div className="shell">
        <header className="topbar">
          <button className="brand brand-btn" onClick={() => leaveToHome()} aria-label="Back to your rooms">
            <Grille on={playing} /><span>Multiroom</span>
          </button>
          <div className="room-title">
            <b>{myRoom?.name || "…"}</b>
            {myRoom?.code && (
              <button className="code-chip num" title="Copy the room code"
                onClick={() => navigator.clipboard?.writeText(myRoom.code).then(() => flash("Code copied"), () => {})}>
                {formatCode(myRoom.code)} <Copy {...I} size={14} />
              </button>
            )}
          </div>
          <div className="top-right">
            <span className={`node-status ${conn.connected ? "" : "off"}`}>
              <i className="dot" aria-hidden="true" />{conn.connected ? "Connected" : "Reconnecting…"}
            </span>
            <button className="btn" onClick={() => setInviteOpen(true)} aria-label="Invite people">
              <QrCode {...I} size={16} /><span className="label">Invite</span>
            </button>
            <Popover.Root>
              <Popover.Trigger asChild>
                <button className="btn quiet account-btn" aria-label="Account">
                  <span className="avatar" aria-hidden="true">{user.display_name.slice(0, 1).toUpperCase()}</span>
                  <ChevronDown {...I} size={14} />
                </button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content className="popover menu" align="end" sideOffset={8}>
                  <p className="menu-who">Signed in as <b>{user.display_name}</b></p>
                  <button className="menu-item" onClick={() => leaveToHome()}>All your rooms</button>
                  {isOwner && <button className="menu-item" onClick={resetCode}>Reset invite code</button>}
                  {myRoom && !isOwner && (
                    <button className="menu-item" onClick={() => handlers.onLeave(myRoom.id)}>Leave this room</button>
                  )}
                  <button className="menu-item" onClick={logout}><LogOut {...I} size={15} />Log out</button>
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
          </div>
        </header>

        <main className="main">
          <div className="listen">
            <Stage track={track} roomState={roomState} core={core} conn={conn} zoneLabel={zoneLabel}
              zoneRooms={myGroup?.rooms.length || 1} presence={presence} leadMs={info.lead_ms}
              health={health} linked={linked} />
            <Queue queue={queue} library={library} current={roomState?.queue_index} playing={playing}
              onJump={(i) => send("jump", { index: i })} onRemove={(id) => send("queue_remove", { item_id: id })}
              onClear={() => send("queue_clear")} uploading={uploading} onUpload={upload}
              onAdd={(t) => { send("queue_add", { track_id: t.id }); flash(`Added ${t.title} to Up next`); }}
              otherRooms={otherRooms} onSend={sendToRoom} userId={user.id} onDeleteTrack={deleteTrack} onEditTrack={editTrack} />
          </div>
        </main>

        <Transport track={track} position={position} playing={playing} canPlay={queue.length > 0}
          onToggle={togglePlay} onPrev={() => send("prev")} onNext={() => send("next")}
          onSeek={(p) => send("seek", { position: p })}
          zoneLabel={zoneLabel || "Rooms"} zoneSynced={linked} onOpenZones={() => setZonesOpen(true)}
          myRoom={myRoom} onVolume={(v) => setVolumes({ [myRoom.id]: v })}
          onVolumeCommit={(v) => setVolumes({ [myRoom.id]: v }, true)} />

        <ZoneDrawer open={zonesOpen} onOpenChange={setZonesOpen} rooms={rooms} roomId={roomId} zoneId={zoneId}
          user={user} handlers={handlers} onCreate={createRoom} onJoin={joinByCode} />
        <Invite open={inviteOpen} onOpenChange={setInviteOpen} info={info} room={myRoom} />
        {toast && <div className="toast" role="status">{toast}</div>}
      </div>
    </MotionConfig>
  );
}
