"""
Multiroom Music Hub: one Flask + Socket.IO node.

Several identical copies of this process (flask1, flask2, flask3) run behind
NGINX. They share nothing in memory; everything they need to agree on lives in
PostgreSQL (durable state) and Redis (pub/sub fan-out, presence, heartbeats).
"""
import eventlet

eventlet.monkey_patch()

try:  # make psycopg2 cooperative with eventlet so one slow query doesn't block the node
    from psycogreen.eventlet import patch_psycopg

    patch_psycopg()
except ImportError:  # pragma: no cover
    pass

import hashlib
import json
import os
import random
import re
import secrets
import time
import uuid
from functools import wraps

import redis as redis_lib
from flask import Flask, g, jsonify, request
from flask_socketio import ConnectionRefusedError, SocketIO, emit, join_room, leave_room
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import library
from models import PlaybackState, QueueItem, Room, RoomMember, Track, User, db

SERVER_ID = os.environ.get("SERVER_ID", f"node-{os.getpid()}")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///music.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
MEDIA_DIR = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(__file__), "..", "media"))
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip()
PORT = int(os.environ.get("PORT", "5000"))
# Every play/seek/next is scheduled this far in the future so that all devices
# receive the command before the moment they are supposed to start.
LEAD_MS = int(os.environ.get("START_LEAD_MS", "600"))
HEARTBEAT_TTL = 3  # seconds; a node that misses heartbeats for this long is considered dead
STATUS_TTL = 8  # seconds; a device that stops reporting for this long is shown as "not responding"
LIVE_TTL = 24 * 3600  # seconds; live playback state is re-read from PostgreSQL after this
# Device health thresholds (absolute drift between a device and the room's shared timeline)
DRIFT_OK_MS = 100  # people can't hear offsets this small between separate speakers; Safari wobbles ~30-80 ms
DRIFT_BAD_MS = 300

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
db.init_app(app)

# message_queue=Redis is what makes this a cluster: socketio.emit(..., to=room) on
# ANY node is published to Redis and every node delivers it to its own sockets.
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    message_queue=REDIS_URL,
    async_mode="eventlet",
    ping_interval=10,
    ping_timeout=10,
)
r = redis_lib.from_url(REDIS_URL, decode_responses=True)

metrics = {"events": 0, "http": 0, "live_hits": 0, "live_misses": 0}
local_clients = {}  # sid -> info dict, for sockets connected to THIS node
local_status = {}  # sid -> {ms, health, drift_ms} of the last status report a local device sent
dirty_rooms = set()  # rooms whose presence list must be re-broadcast
BOOT_MS = int(time.time() * 1000)


def now_ms():
    return int(time.time() * 1000)


def log(*args):
    print(f"[{SERVER_ID}]", *args, flush=True)


# ---------------------------------------------------------------------------
# Presence & cluster bookkeeping in Redis
#   cluster:nodes            set of node ids ever seen
#   node:<id>                heartbeat JSON, expires after HEARTBEAT_TTL
#   clients                  hash sid -> {server, room, name, kind}
#   room:<id>:members        hash sid -> same JSON, for fast per-room lookup
#   live:<room_id>           live playback state of a zone (see "Live state" below)
#   status:<sid>             latest status report from a device, expires after STATUS_TTL
# ---------------------------------------------------------------------------

def save_client(sid, info):
    raw = json.dumps(info)
    pipe = r.pipeline()
    pipe.hset("clients", sid, raw)
    if info.get("room"):
        pipe.hset(f"room:{info['room']}:members", sid, raw)
    pipe.execute()


def drop_client(sid, info):
    pipe = r.pipeline()
    pipe.hdel("clients", sid)
    if info and info.get("room"):
        pipe.hdel(f"room:{info['room']}:members", sid)
        dirty_rooms.add(info["room"])
    pipe.execute()


def alive_nodes():
    nodes = sorted(r.smembers("cluster:nodes"))
    beats = r.mget([f"node:{n}" for n in nodes]) if nodes else []
    return {n: json.loads(b) for n, b in zip(nodes, beats) if b}, nodes


# ---------------------------------------------------------------------------
# Zones: rooms linked together play the leader room's queue in sync.
# Socket.IO rooms used:
#   <room_id>        every socket whose device sits in that room (presence)
#   play:<leader_id> every socket that should hear that zone's playback
# ---------------------------------------------------------------------------

def leader_of(room_id):
    room = db.session.get(Room, room_id)
    if room is None:
        return None
    return room.group_leader or room.id


def zone_room_ids(leader_id):
    rows = Room.query.filter((Room.id == leader_id) | (Room.group_leader == leader_id)).all()
    return [rm.id for rm in sorted(rows, key=lambda rm: (rm.id != leader_id, rm.created_at))]


def presence_payload(leader_id):
    """Everyone listening to one zone: devices in the leader room and every linked room."""
    alive, _ = alive_nodes()
    names = {rm.id: rm.name for rm in Room.query.all()}
    devices, virtual, per_server = [], 0, {}
    for rid in zone_room_ids(leader_id):
        for raw in r.hvals(f"room:{rid}:members"):
            m = json.loads(raw)
            if m.get("server") not in alive:
                continue
            per_server[m["server"]] = per_server.get(m["server"], 0) + 1
            if m.get("kind") == "virtual":
                virtual += 1
            else:
                devices.append({"name": m["name"], "server": m["server"], "sid": m.get("sid"),
                                "room_id": rid, "room": names.get(rid, "")})
    # attach each room node's latest status report (one round trip for the whole zone)
    reports = r.mget([f"status:{d['sid']}" for d in devices]) if devices else []
    for d, raw in zip(devices, reports):
        d["status"] = json.loads(raw) if raw else None
        d["health"] = d["status"]["health"] if d["status"] else "silent"
    counts = {}
    for d in devices:
        counts[d["health"]] = counts.get(d["health"], 0) + 1
    return {
        "room_id": leader_id,
        "devices": sorted(devices, key=lambda d: (d["room"].lower(), d["name"].lower())),
        "virtual": virtual,
        "per_server": per_server,
        "health": counts,
    }


def gc_dead_nodes():
    """Failure detection: remove clients that belonged to nodes whose heartbeat expired."""
    alive, nodes = alive_nodes()
    dead = set(nodes) - set(alive)
    if not dead:
        return
    removed = 0
    for sid, raw in r.hgetall("clients").items():
        info = json.loads(raw)
        if info.get("server") in dead:
            drop_client(sid, info)
            removed += 1
    if removed:
        log(f"cleaned up {removed} clients from dead node(s) {sorted(dead)}")


def mark_silent_devices():
    """A connected device whose status reports stopped (tab frozen, phone asleep, audio
    stack hung) is still 'online' to Socket.IO. Re-broadcast presence once its report
    expires so everyone sees it as not responding."""
    t = now_ms()
    for sid, st in list(local_status.items()):
        info = local_clients.get(sid)
        if not info:
            local_status.pop(sid, None)
            continue
        if info.get("room") and st["health"] != "silent" and t - st["ms"] > STATUS_TTL * 1000:
            st["health"] = "silent"
            dirty_rooms.add(info["room"])


def heartbeat_loop():
    last = dict(metrics)
    last_t = time.time()
    tick = 0
    while True:
        socketio.sleep(1)
        t = time.time()
        dt = max(t - last_t, 1e-3)
        beat = {
            "id": SERVER_ID,
            "ts": now_ms(),
            "boot_ms": BOOT_MS,
            "connections": len(local_clients),
            "devices": sum(1 for c in local_clients.values() if c.get("kind") != "virtual"),
            "virtual": sum(1 for c in local_clients.values() if c.get("kind") == "virtual"),
            "events_per_sec": round((metrics["events"] - last["events"]) / dt, 1),
            "http_per_sec": round((metrics["http"] - last["http"]) / dt, 1),
            "events_total": metrics["events"],
            "http_total": metrics["http"],
            "live_state_hits": metrics["live_hits"],
            "live_state_misses": metrics["live_misses"],
        }
        last, last_t = dict(metrics), t
        try:
            pipe = r.pipeline()
            pipe.set(f"node:{SERVER_ID}", json.dumps(beat), ex=HEARTBEAT_TTL)
            pipe.sadd("cluster:nodes", SERVER_ID)
            pipe.execute()
            tick += 1
            if tick % 2 == 0:
                gc_dead_nodes()
            mark_silent_devices()
        except redis_lib.RedisError as exc:
            log("heartbeat failed:", exc)


def presence_loop():
    """Batch presence broadcasts so 100 virtual listeners joining = a few messages, not 100."""
    while True:
        socketio.sleep(0.5)
        if not dirty_rooms:
            continue
        rooms = list(dirty_rooms)
        dirty_rooms.clear()
        try:
            with app.app_context():
                leaders = {leader_of(room_id) for room_id in rooms}
                leaders.discard(None)
                for leader_id in leaders:
                    socketio.emit("presence", presence_payload(leader_id), to=f"play:{leader_id}")
                db.session.remove()
        except Exception as exc:  # never let the loop die
            log("presence failed:", repr(exc))


# ---------------------------------------------------------------------------
# Playback state machine (PostgreSQL row lock = one writer at a time per room)
# ---------------------------------------------------------------------------

def queue_items(room_id):
    return QueueItem.query.filter_by(room_id=room_id).order_by(QueueItem.position, QueueItem.id).all()


def current_position(state, at_ms):
    if state.is_playing and state.anchor_ms:
        return max(0.0, state.offset + (at_ms - state.anchor_ms) / 1000.0)
    return state.offset


def state_payload(state, items):
    track = None
    if state.queue_index is not None and 0 <= state.queue_index < len(items):
        track = items[state.queue_index].track.to_dict()
    return {
        "room_id": state.room_id,
        "version": state.version,
        "is_playing": bool(state.is_playing and track),
        "queue_index": state.queue_index,
        "offset": state.offset,
        "anchor_ms": state.anchor_ms,
        "server_ms": now_ms(),
        "track": track,
        "action": state.last_action,
        "updated_by": state.updated_by,
        "served_by": SERVER_ID,
    }


def queue_payload(room_id, items=None):
    items = items if items is not None else queue_items(room_id)
    return {"room_id": room_id, "items": [i.to_dict() for i in items]}


# ---------------------------------------------------------------------------
# Live state in Redis
#
# PostgreSQL is the durable record and the only place commands are applied (under
# a row lock). After every committed command the new playback state is also
# written to Redis as `live:<room_id>`, so reads (joining a room, opening the app,
# the room list) are served from memory by any node without touching PostgreSQL.
#
# Commands on different nodes can finish in any order, so the write is a
# compare-and-set on `version`: an older state can never overwrite a newer one.
# If Redis is wiped (or the key expires) the next read falls back to PostgreSQL
# and repopulates the cache.
# ---------------------------------------------------------------------------

LIVE_FIELDS = ("room_id", "version", "is_playing", "queue_index", "offset", "anchor_ms",
               "track", "action", "updated_by")
_live_cas = r.register_script("""
local cur = redis.call('GET', KEYS[1])
if cur then
  local ok, v = pcall(function() return cjson.decode(cur)['version'] end)
  if ok and v and tonumber(v) >= tonumber(ARGV[2]) then return 0 end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
return 1
""")


def live_key(room_id):
    return f"live:{room_id}"


def cache_live_state(payload):
    data = {k: payload.get(k) for k in LIVE_FIELDS}
    try:
        _live_cas(keys=[live_key(data["room_id"])], args=[json.dumps(data), data["version"], LIVE_TTL])
    except redis_lib.RedisError as exc:  # the cache is an optimisation; PostgreSQL still has it
        log("live state cache write failed:", exc)


def live_state(room_id, items=None):
    """Current playback state of a zone: from Redis if cached, else PostgreSQL."""
    raw = None
    try:
        raw = r.get(live_key(room_id))
    except redis_lib.RedisError:
        pass
    if raw:
        metrics["live_hits"] += 1
        data = json.loads(raw)
        data.update(server_ms=now_ms(), served_by=SERVER_ID, source="redis")
        return data
    metrics["live_misses"] += 1
    state = db.session.get(PlaybackState, room_id)
    if state is None:
        return None
    payload = state_payload(state, items if items is not None else queue_items(room_id))
    cache_live_state(payload)
    payload["source"] = "postgres"
    return payload


QUEUE_ACTIONS = {"queue_add", "queue_remove", "queue_clear"}


def apply_command(room_id, action, data, by):
    """
    Applies one command atomically. SELECT ... FOR UPDATE locks this room's row, so
    if two devices on two different nodes press buttons at the same instant, one
    waits for the other and both see a consistent state. Returns None if the
    command was a no-op (e.g. a duplicate track_ended).
    """
    state = (
        db.session.query(PlaybackState).filter_by(room_id=room_id).with_for_update().one_or_none()
    )
    if state is None:
        db.session.rollback()
        raise ValueError("Room not found")
    items = queue_items(room_id)
    t = now_ms()
    pos = current_position(state, t)
    n = len(items)
    qi = state.queue_index

    def start_at(offset, playing):
        state.offset = max(0.0, float(offset))
        state.is_playing = playing
        state.anchor_ms = t + LEAD_MS if playing else t

    if action == "play":
        if not n:
            db.session.rollback()
            raise ValueError("The queue is empty. Add a song from the library first.")
        if state.is_playing and qi is not None:
            db.session.rollback()
            return None
        if qi is None or qi >= n:
            state.queue_index, pos = 0, 0.0
        start_at(pos, True)
    elif action == "pause":
        if not state.is_playing:
            db.session.rollback()
            return None
        start_at(pos, False)
    elif action == "seek":
        start_at(data.get("position", 0), state.is_playing)
    elif action in ("next", "prev", "jump", "track_ended"):
        if not n:
            db.session.rollback()
            return None
        if action == "track_ended":
            # Every device in the room reports the end of the song; only the first
            # report (matching the current version) advances. The rest are ignored.
            if data.get("version") != state.version:
                db.session.rollback()
                return None
            new_index = (qi or 0) + 1
        elif action == "next":
            new_index = (qi if qi is not None else -1) + 1
        elif action == "prev":
            new_index = (qi or 0) - 1 if pos < 3 else (qi or 0)
        else:
            new_index = int(data.get("index", 0))
        state.queue_index = new_index % n  # the queue loops so the music never stops
        start_at(0, state.is_playing or action == "jump")
    elif action == "queue_add":
        track = db.session.get(Track, int(data.get("track_id", 0)))
        if track is None:
            db.session.rollback()
            raise ValueError("Unknown track")
        last_pos = items[-1].position if items else -1
        item = QueueItem(room_id=room_id, track_id=track.id, position=last_pos + 1)
        db.session.add(item)
        db.session.flush()
        items.append(item)
        if qi is None:
            state.queue_index = 0
            start_at(0, False)
    elif action == "queue_remove":
        idx = next((i for i, it in enumerate(items) if it.id == data.get("item_id")), None)
        if idx is None:
            db.session.rollback()
            return None
        db.session.delete(items.pop(idx))
        if not items:
            state.queue_index = None
            start_at(0, False)
        elif qi is not None and idx < qi:
            state.queue_index = qi - 1
        elif idx == qi:
            state.queue_index = qi % len(items)
            start_at(0, state.is_playing)
    elif action == "queue_clear":
        for it in items:
            db.session.delete(it)
        items = []
        state.queue_index = None
        start_at(0, False)
    else:
        db.session.rollback()
        raise ValueError(f"Unknown action {action!r}")

    state.version += 1
    state.last_action = action
    state.updated_by = f"{by} via {SERVER_ID}"
    db.session.flush()
    # Build the broadcast while we still hold the row lock: after commit the row could
    # already be changed by another node, and we must announce exactly what we wrote.
    payload = state_payload(state, items)
    queue = queue_payload(room_id, items) if action in QUEUE_ACTIONS else None
    db.session.commit()
    cache_live_state(payload)
    return payload, queue


# ---------------------------------------------------------------------------
# Accounts and access control
#
# Sessions live in Redis (shared by every node), so a user who logged in through
# flask1 is recognised by flask2 and flask3 with no sticky sessions. Only a
# SHA-256 of each token is stored, so a Redis dump can't be replayed as logins.
# ---------------------------------------------------------------------------

SESSION_TTL = 30 * 24 * 3600
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L, so codes are easy to read aloud
CODE_LEN = 6  # 31^6 ≈ 887 million codes; guessing is also rate limited
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
DUMMY_HASH = generate_password_hash("timing-equaliser")


def token_key(token):
    return "session:" + hashlib.sha256(token.encode()).hexdigest()


def new_session(user):
    token = secrets.token_urlsafe(32)
    r.setex(token_key(token), SESSION_TTL, user.id)
    return token


def user_from_token(token):
    if not token or len(token) > 200:
        return None
    uid = r.get(token_key(token))
    return db.session.get(User, uid) if uid else None


def bearer_token():
    h = request.headers.get("Authorization", "")
    return h[7:].strip() if h.startswith("Bearer ") else None


def client_ip():
    return request.headers.get("X-Real-IP") or request.remote_addr or "?"


def too_many(bucket, limit, window_s):
    """Fixed-window counter in Redis, shared by all nodes. True once over the limit."""
    key = f"rl:{bucket}"
    n = r.incr(key)
    if n == 1:
        r.expire(key, window_s)
    return n > limit


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = user_from_token(bearer_token())
        if user is None:
            return jsonify({"error": "Log in to continue."}), 401
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def membership(user_id, room_id):
    if not user_id or not room_id:
        return None
    return db.session.get(RoomMember, (room_id, user_id))


def member_user_ids(room_ids):
    if not room_ids:
        return set()
    return {m.user_id for m in RoomMember.query.filter(RoomMember.room_id.in_(list(room_ids))).all()}


def notify_members(room_ids, event, payload, skip_sid=None):
    """Send an event only to the people who belong to these rooms (every socket
    joins `user:<id>` on connect), so private rooms never leak to other users."""
    for uid in member_user_ids(room_ids):
        socketio.emit(event, payload, to=f"user:{uid}", skip_sid=skip_sid)


def normalize_code(code):
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())[:CODE_LEN]


def new_room_code():
    for _ in range(25):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
        if not Room.query.filter_by(code=code).first():
            return code
    raise RuntimeError("could not allocate a room code")


def not_found():
    # same answer for "doesn't exist" and "not yours", so ids can't be probed
    return jsonify({"error": "Room not found."}), 404


# ---------------------------------------------------------------------------
# REST API (stateless: NGINX round-robins these across all nodes)
# ---------------------------------------------------------------------------

@app.before_request
def count_http():
    metrics["http"] += 1


@app.after_request
def served_by(resp):
    resp.headers["X-Served-By"] = SERVER_ID
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/api/health")
def health():
    return jsonify({"server": SERVER_ID, "status": "ok"})


@app.get("/api/info")
def info():
    public_url = f"http://{PUBLIC_HOST}" if PUBLIC_HOST else ""
    return jsonify({"server": SERVER_ID, "public_url": public_url, "lead_ms": LEAD_MS})


@app.get("/api/time")
def server_time():
    return jsonify({"server_ms": time.time() * 1000, "server": SERVER_ID})


@app.post("/api/auth/signup")
def signup():
    if too_many(f"signup:{client_ip()}", 30, 3600):
        return jsonify({"error": "Too many new accounts from this network. Try again in an hour."}), 429
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip().lower()
    password = str(data.get("password") or "")
    if not USERNAME_RE.match(username):
        return jsonify({"error": "Usernames are 3 to 32 characters: letters, numbers, dots, dashes or underscores."}), 400
    if len(password) < 8:
        return jsonify({"error": "Use at least 8 characters for your password."}), 400
    if len(password) > 200:
        return jsonify({"error": "That password is too long."}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "That username is taken. Try another one."}), 409
    display = str(data.get("display_name") or data.get("username") or username).strip()[:40] or username
    user = User(id=str(uuid.uuid4()), username=username, display_name=display,
                password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "That username is taken. Try another one."}), 409
    return jsonify({"token": new_session(user), "user": user.to_dict()}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip().lower()
    password = str(data.get("password") or "")
    bucket = f"login:{username}:{client_ip()}"
    if int(r.get(f"rl:{bucket}") or 0) >= 10:
        return jsonify({"error": "Too many wrong passwords. Wait 10 minutes and try again."}), 429
    user = User.query.filter_by(username=username).first() if username else None
    # always run one hash check, so response time doesn't reveal which usernames exist
    ok = check_password_hash(user.password_hash if user else DUMMY_HASH, password)
    if not user or not ok:
        too_many(bucket, 10, 600)
        return jsonify({"error": "Wrong username or password."}), 401
    r.delete(f"rl:{bucket}")
    return jsonify({"token": new_session(user), "user": user.to_dict()})


@app.post("/api/auth/logout")
def logout():
    token = bearer_token()
    if token:
        r.delete(token_key(token))
    return jsonify({"ok": True})


@app.get("/api/auth/me")
@login_required
def me():
    return jsonify({"user": g.user.to_dict()})


@app.get("/api/tracks")
@login_required
def list_tracks():
    tracks = Track.query.order_by(Track.uploaded, Track.title).all()
    return jsonify([t.to_dict() for t in tracks])


@app.post("/api/tracks")
@login_required
def upload_track():
    if too_many(f"upload:{g.user.id}", 60, 3600):
        return jsonify({"error": "Upload limit reached. Try again in an hour."}), 429
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file uploaded"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in library.AUDIO_EXT:
        return jsonify({"error": f"Unsupported file type {ext}"}), 400
    os.makedirs(os.path.join(MEDIA_DIR, "uploads"), exist_ok=True)
    # the stored name is random, never the uploaded name, so paths can't be injected
    rel = f"uploads/{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(MEDIA_DIR, rel)
    f.save(path)
    tags = library.read_tags(path)
    if not tags["duration"]:
        os.remove(path)
        return jsonify({"error": "That file doesn't look like audio we can play."}), 400
    tag_title = tags["title"]
    if tag_title.lower().replace(" ", "") == os.path.splitext(os.path.basename(rel))[0].lower():
        tag_title = None  # read_tags fell back to our random stored name, not a real tag
    title, artist = library.guess_title_artist(f.filename, {"title": tag_title, "artist": tags["artist"]})
    stem = os.path.splitext(os.path.basename(rel))[0]
    cover = library.extract_embedded_cover(path, MEDIA_DIR, stem)  # before re-encoding drops it
    # Re-encode to the library's standard format so every browser seeks and syncs it
    # accurately (see library.normalize_audio). If ffmpeg is missing, keep the original.
    if library.ffmpeg_available() and not library.is_normalized(path, tags):
        norm_rel = f"uploads/{stem}.mp3"
        norm_path = os.path.join(MEDIA_DIR, norm_rel)
        if library.normalize_audio(path, norm_path):
            if os.path.abspath(path) != os.path.abspath(norm_path):
                os.remove(path)
            rel, path = norm_rel, norm_path
            fresh = library.read_tags(path)
            for k in ("codec", "bitrate", "sample_rate", "channels"):
                tags[k] = fresh[k]
            tags["duration"] = fresh["duration"] or tags["duration"]
    track = Track(
        filename=rel,
        title=(request.form.get("title") or title)[:200],
        artist=(request.form.get("artist") or artist)[:200],
        genre="Upload",
        color=random.choice(library.PALETTE),
        duration=tags["duration"],
        codec=tags["codec"],
        bitrate=tags["bitrate"],
        sample_rate=tags["sample_rate"],
        channels=tags["channels"],
        cover=cover,
        uploaded=True,
        uploaded_by=g.user.id,
    )
    db.session.add(track)
    db.session.commit()
    socketio.emit("library_changed", {"track": track.to_dict(), "by": SERVER_ID})
    return jsonify(track.to_dict()), 201


def remove_track_everywhere(track_id, by):
    """Takes a song out of every room's queue through the normal locked state machine,
    so a room playing it moves on cleanly and every device hears the change."""
    room_ids = sorted({qi.room_id for qi in QueueItem.query.filter_by(track_id=track_id).all()})
    for room_id in room_ids:
        for item in QueueItem.query.filter_by(room_id=room_id, track_id=track_id).all():
            result = apply_command(room_id, "queue_remove", {"item_id": item.id}, by)
            if result:
                payload, queue = result
                socketio.emit("state", payload, to=f"play:{room_id}")
                socketio.emit("queue", queue, to=f"play:{room_id}")
    return room_ids


def delete_track_files(track):
    """Deletes an upload's audio file and its extracted cover (never anything outside uploads/)."""
    for rel in (track.filename, track.cover):
        if rel and rel.startswith("uploads/") and ".." not in rel:
            try:
                os.remove(os.path.join(MEDIA_DIR, rel))
            except OSError:
                pass


@app.delete("/api/tracks/<int:track_id>")
@login_required
def delete_track(track_id):
    """Delete an uploaded song: whoever uploaded it can (older uploads with no recorded
    uploader can be removed by anyone). The 10 built-in songs can't be deleted."""
    track = db.session.get(Track, track_id)
    if track is None:
        return jsonify({"error": "That song no longer exists."}), 404
    if not track.uploaded:
        return jsonify({"error": "Built-in songs can't be deleted."}), 403
    if track.uploaded_by and track.uploaded_by != g.user.id:
        return jsonify({"error": "Only the person who uploaded this song can delete it."}), 403
    rooms = remove_track_everywhere(track.id, f"{g.user.display_name} (deleted a song)")
    delete_track_files(track)
    db.session.delete(db.session.get(Track, track_id))
    db.session.commit()
    socketio.emit("library_changed", {"deleted": track_id, "by": SERVER_ID})
    if rooms:
        notify_members(rooms, "rooms_changed", {"by": SERVER_ID})
    return jsonify({"ok": True, "removed_from_rooms": len(rooms)})


@app.patch("/api/tracks/<int:track_id>")
@login_required
def edit_track(track_id):
    """Rename an uploaded song: {"title", "artist"}. Same permission as deleting."""
    track = db.session.get(Track, track_id)
    if track is None:
        return jsonify({"error": "That song no longer exists."}), 404
    if not track.uploaded:
        return jsonify({"error": "Built-in songs can't be edited."}), 403
    if track.uploaded_by and track.uploaded_by != g.user.id:
        return jsonify({"error": "Only the person who uploaded this song can edit it."}), 403
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", track.title)).strip()[:200]
    artist = str(data.get("artist", track.artist)).strip()[:200] or "Unknown artist"
    if not title:
        return jsonify({"error": "Give the song a title."}), 400
    track.title, track.artist = title, artist
    db.session.commit()
    announce_track_changed(track)
    return jsonify(track.to_dict())


def announce_track_changed(track):
    """Song details changed: drop cached live state that embeds the old details, and
    tell every device so titles update without touching playback."""
    rooms = {qi.room_id for qi in QueueItem.query.filter_by(track_id=track.id).all()}
    leaders = {leader_of(rid) for rid in rooms} - {None}
    for leader_id in leaders:
        r.delete(live_key(leader_id))
    socketio.emit("track_updated", track.to_dict())
    if rooms:
        notify_members(rooms, "rooms_changed", {"by": SERVER_ID})


def fix_raw_upload_names():
    """Older uploads were named after their raw filename ("artist-song-title-123456");
    give them a readable title and artist once."""
    fixed = 0
    for t in Track.query.filter_by(uploaded=True).all():
        if t.artist in (None, "", "Unknown artist") and library.looks_like_raw_filename(t.title):
            title, artist = library.guess_title_artist(t.title + ".mp3")
            if (title, artist) != (t.title, t.artist):
                t.title, t.artist = title, artist
                fixed += 1
    db.session.commit()
    if fixed:
        for key in r.scan_iter("live:*"):
            r.delete(key)  # cached states may embed the old names
    return fixed


def prune_missing_uploads():
    """Uploads whose audio file is gone (e.g. the project folder was replaced) can never
    play, so drop them from the library and from every queue at startup."""
    gone = [t for t in Track.query.filter_by(uploaded=True).all()
            if not os.path.exists(os.path.join(MEDIA_DIR, t.filename))]
    for t in gone:
        remove_track_everywhere(t.id, "library cleanup")
        db.session.delete(db.session.get(Track, t.id))
    db.session.commit()
    return len(gone)


def room_summary(room, playing, alive, roles, member_counts):
    members = [json.loads(v) for v in r.hvals(f"room:{room.id}:members")]
    members = [m for m in members if m.get("server") in alive]
    title, artist, cover, is_playing = playing.get(room.group_leader or room.id, (None, None, None, False))
    return {
        **room.to_dict(),
        "role": roles.get(room.id, "member"),
        "members": member_counts.get(room.id, 0),
        "devices": sum(1 for m in members if m.get("kind") != "virtual"),
        "is_playing": is_playing,
        "now_playing": title,
        "now_playing_artist": artist,
        "now_playing_cover": cover,
    }


@app.get("/api/rooms")
@login_required
def list_rooms():
    """Only the rooms you belong to. There is no way to list anyone else's rooms."""
    mine = RoomMember.query.filter_by(user_id=g.user.id).all()
    roles = {m.room_id: m.role for m in mine}
    rooms = Room.query.filter(Room.id.in_(list(roles))).order_by(Room.created_at).all() if roles else []
    leaders = {rm.group_leader or rm.id for rm in rooms}
    playing = {}
    for leader_id in leaders:
        s = live_state(leader_id)  # Redis first, PostgreSQL only on a cache miss
        if s and s.get("track"):
            t = s["track"]
            playing[leader_id] = (t.get("title"), t.get("artist"), t.get("cover"), bool(s.get("is_playing")))
    counts = {}
    if roles:
        for m in RoomMember.query.filter(RoomMember.room_id.in_(list(roles))).all():
            counts[m.room_id] = counts.get(m.room_id, 0) + 1
    alive, _ = alive_nodes()
    return jsonify([room_summary(rm, playing, alive, roles, counts) for rm in rooms])


@app.post("/api/rooms")
@login_required
def create_room():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:60]
    if not name:
        return jsonify({"error": "Give the room a name."}), 400
    if RoomMember.query.filter_by(user_id=g.user.id, role="owner").count() >= 20:
        return jsonify({"error": "You can own up to 20 rooms. Delete one to make another."}), 400
    room = Room(id=str(uuid.uuid4()), name=name, code=new_room_code(), owner_id=g.user.id)
    db.session.add(room)
    db.session.flush()
    db.session.add(PlaybackState(room_id=room.id))
    db.session.add(RoomMember(room_id=room.id, user_id=g.user.id, role="owner"))
    db.session.commit()
    notify_members([room.id], "rooms_changed", {"by": SERVER_ID})
    return jsonify({**room.to_dict(), "role": "owner"}), 201


@app.post("/api/rooms/join")
@login_required
def join_by_code():
    code = normalize_code((request.get_json(silent=True) or {}).get("code"))
    bucket = f"join:{g.user.id}"
    if int(r.get(f"rl:{bucket}") or 0) >= 15:
        return jsonify({"error": "Too many wrong codes. Wait 10 minutes and try again."}), 429
    room = Room.query.filter_by(code=code).first() if len(code) == CODE_LEN else None
    if room is None:
        too_many(bucket, 15, 600)
        return jsonify({"error": "No room has that code. Check it with whoever invited you."}), 404
    if not membership(g.user.id, room.id):
        db.session.add(RoomMember(room_id=room.id, user_id=g.user.id, role="member"))
        db.session.commit()
        notify_members([room.id], "rooms_changed", {"by": SERVER_ID})
    return jsonify({**room.to_dict(), "role": membership(g.user.id, room.id).role})


@app.post("/api/rooms/<room_id>/code")
@login_required
def reset_code(room_id):
    """Owner only: issue a new invite code. The old one stops working; members stay."""
    m = membership(g.user.id, room_id)
    if not m:
        return not_found()
    if m.role != "owner":
        return jsonify({"error": "Only the room's owner can reset its code."}), 403
    room = db.session.get(Room, room_id)
    room.code = new_room_code()
    db.session.commit()
    notify_members([room.id], "rooms_changed", {"by": SERVER_ID})
    return jsonify(room.to_dict())


def kick_sockets(room_ids, user_id=None):
    """Tell devices to drop a room they may no longer be in (deleted, or they left it)."""
    for rid in room_ids:
        socketio.emit("room_closed", {"room_id": rid, "user_id": user_id}, to=rid)


@app.post("/api/rooms/<room_id>/leave")
@login_required
def leave_room_api(room_id):
    m = membership(g.user.id, room_id)
    if not m:
        return not_found()
    if m.role == "owner":
        return jsonify({"error": "You own this room. Delete it instead, or keep it."}), 400
    db.session.delete(m)
    db.session.commit()
    kick_sockets([room_id], g.user.id)
    notify_members([room_id], "rooms_changed", {"by": SERVER_ID})
    socketio.emit("rooms_changed", {"by": SERVER_ID}, to=f"user:{g.user.id}")
    return jsonify({"ok": True})


@app.delete("/api/rooms/<room_id>")
@login_required
def delete_room(room_id):
    m = membership(g.user.id, room_id)
    if not m:
        return not_found()
    if m.role != "owner":
        return jsonify({"error": "Only the room's owner can delete it."}), 403
    room = db.session.get(Room, room_id)
    member_ids = member_user_ids([room_id])
    followers = Room.query.filter_by(group_leader=room_id).all()
    for follower in followers:
        follower.group_leader = None
    if room.group_leader:
        dirty_rooms.add(room.group_leader)
    QueueItem.query.filter_by(room_id=room_id).delete()
    PlaybackState.query.filter_by(room_id=room_id).delete()
    RoomMember.query.filter_by(room_id=room_id).delete()
    db.session.delete(room)
    db.session.commit()
    r.delete(live_key(room_id))
    kick_sockets([room_id])
    if followers:
        announce_regroup({f.id for f in followers})
    for uid in member_ids:
        socketio.emit("rooms_changed", {"by": SERVER_ID}, to=f"user:{uid}")
    return jsonify({"ok": True})


@app.get("/api/rooms/<room_id>")
@login_required
def get_room(room_id):
    if not membership(g.user.id, room_id):
        return not_found()
    leader_id = leader_of(room_id)
    state = live_state(leader_id) if leader_id else None
    if state is None:
        return not_found()
    return jsonify({"zone_id": leader_id, "state": state, "queue": queue_payload(leader_id)})


@app.post("/api/rooms/<room_id>/queue")
@login_required
def send_to_room(room_id):
    """Assign music to any of your rooms from wherever you are, without switching to it.
    {"track_id": 3, "play": false}: add to that room's queue; with "play": true it
    starts playing there right away. Goes through the same locked state machine as
    the in-room buttons, so it is safe against simultaneous commands."""
    if not membership(g.user.id, room_id):
        return not_found()
    data = request.get_json(silent=True) or {}
    leader_id = leader_of(room_id)
    who = f"{g.user.display_name} (remote)"
    try:
        payload, queue = apply_command(leader_id, "queue_add", {"track_id": data.get("track_id")}, who)
        if data.get("play"):
            payload, _ = apply_command(leader_id, "jump", {"index": len(queue["items"]) - 1}, who)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    socketio.emit("state", payload, to=f"play:{leader_id}")
    socketio.emit("queue", queue, to=f"play:{leader_id}")
    notify_members(zone_room_ids(leader_id), "rooms_changed", {"by": SERVER_ID})
    return jsonify({"ok": True, "zone_id": leader_id, "state": payload, "queue_length": len(queue["items"])})


@app.get("/api/rooms/<room_id>/devices")
@login_required
def room_devices(room_id):
    """The central controller's view of the room nodes: every device in the zone with
    its latest status report (playing/paused/buffering, drift, health, last report)."""
    if not membership(g.user.id, room_id):
        return not_found()
    return jsonify(presence_payload(leader_of(room_id)))


def announce_regroup(room_ids):
    """Tell devices in the affected rooms to re-join (switching zone), and refresh members' room lists."""
    for rid in room_ids:
        socketio.emit("regroup", {"rooms": sorted(room_ids), "by": SERVER_ID}, to=rid)
    notify_members(room_ids, "rooms_changed", {"by": SERVER_ID})


@app.post("/api/rooms/<room_id>/link")
@login_required
def link_room(room_id):
    """Link room_id into the zone that `to` belongs to. You must be a member of both rooms."""
    data = request.get_json(silent=True) or {}
    to_id = data.get("to") or ""
    if not membership(g.user.id, room_id) or not membership(g.user.id, to_id):
        return not_found()
    room, target = db.session.get(Room, room_id), db.session.get(Room, to_id)
    leader_id = target.group_leader or target.id
    if room.id == leader_id or room.group_leader == leader_id:
        return jsonify({"ok": True, "leader": leader_id})
    affected = {room.id}
    # if this room was leading its own zone, its followers come along
    for follower in Room.query.filter_by(group_leader=room.id).all():
        follower.group_leader = leader_id
        affected.add(follower.id)
    room.group_leader = leader_id
    db.session.commit()
    announce_regroup(affected | {leader_id})
    dirty_rooms.update(affected | {leader_id})
    return jsonify({"ok": True, "leader": leader_id})


@app.post("/api/rooms/<room_id>/unlink")
@login_required
def unlink_room(room_id):
    """Take a room out of its zone. Unlinking the zone's leader splits the whole zone up."""
    if not membership(g.user.id, room_id):
        return not_found()
    room = db.session.get(Room, room_id)
    affected = set()
    if room.group_leader:
        affected.add(room.id)
        old_leader = room.group_leader
        room.group_leader = None
        dirty_rooms.add(old_leader)
    else:
        for follower in Room.query.filter_by(group_leader=room.id).all():
            follower.group_leader = None
            affected.add(follower.id)
    db.session.commit()
    if affected:
        announce_regroup(affected | {room.id})
        dirty_rooms.update(affected | {room.id})
    return jsonify({"ok": True})


@app.get("/api/cluster")
def cluster():
    """Node health for the (unlisted) /cluster dashboard. Counts only, no room or user data."""
    alive, nodes = alive_nodes()
    out = []
    for n in nodes:
        beat = alive.get(n)
        out.append({"id": n, "alive": beat is not None, **(beat or {})})
    total = sum(b.get("connections", 0) for b in alive.values())
    return jsonify({"served_by": SERVER_ID, "server_ms": now_ms(), "nodes": out, "total_connections": total})


# ---------------------------------------------------------------------------
# Socket.IO (long-lived WebSockets: NGINX sends each new one to the least-busy node)
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect(auth=None):
    auth = auth if isinstance(auth, dict) else {}
    virtual = auth.get("kind") == "virtual"
    user = None
    if not virtual:
        user = user_from_token(auth.get("token"))
        if user is None:
            # the client sees connect_error "unauthorized" and shows the login screen
            raise ConnectionRefusedError("unauthorized")
    device = str(auth.get("device") or "device")[:20]
    info = {
        "sid": request.sid,
        "server": SERVER_ID,
        "name": f"{user.display_name}'s {device}" if user else "Virtual listener",
        "user_id": user.id if user else None,
        "kind": "virtual" if virtual else "device",
        "room": None,
        "since": now_ms(),
    }
    if user:
        join_room(f"user:{user.id}")
    local_clients[request.sid] = info
    save_client(request.sid, info)
    metrics["events"] += 1
    emit("welcome", {"server": SERVER_ID, "sid": request.sid, "server_ms": time.time() * 1000})


@socketio.on("disconnect")
def on_disconnect(*_):
    info = local_clients.pop(request.sid, None)
    local_status.pop(request.sid, None)
    r.delete(f"status:{request.sid}")
    drop_client(request.sid, info)


@socketio.on("time_sync")
def on_time_sync(_data=None):
    """Cristian's algorithm: the client measures round-trip time around this call."""
    metrics["events"] += 1
    return {"server_ms": time.time() * 1000, "server": SERVER_ID}


STATUS_STATES = {"playing", "paused", "idle", "starting", "buffering", "blocked"}


def device_health(state, drift_ms):
    if state == "blocked":
        return "blocked"  # browser autoplay policy: needs a tap before it can make sound
    if state == "buffering":
        return "buffering"
    if state != "playing":
        return "idle"
    if drift_ms is None or abs(drift_ms) <= DRIFT_OK_MS:
        return "in_sync"
    return "correcting" if abs(drift_ms) <= DRIFT_BAD_MS else "out_of_sync"


@socketio.on("status")
def on_status(data):
    """Room nodes report what they are actually doing every few seconds:
    {state, position, drift_ms, version, track_id}. The controller derives a health
    value, keeps the report in Redis (visible to every node) and re-broadcasts the
    zone's speaker list when a device's health changes."""
    info = local_clients.get(request.sid)
    if not info or info.get("kind") == "virtual" or not info.get("room"):
        return {"ok": False}
    data = data if isinstance(data, dict) else {}
    state = data.get("state") if data.get("state") in STATUS_STATES else "idle"

    def num(v, lo, hi):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return round(min(hi, max(lo, v)), 1) if v == v else None

    drift = num(data.get("drift_ms"), -60000, 60000)
    report = {
        "state": state,
        "health": device_health(state, drift),
        "position": num(data.get("position"), 0, 86400),
        "drift_ms": drift if state == "playing" else None,
        "version": data.get("version") if isinstance(data.get("version"), int) else None,
        "track_id": data.get("track_id") if isinstance(data.get("track_id"), int) else None,
        "reported_ms": now_ms(),
        "server": SERVER_ID,
    }
    r.set(f"status:{request.sid}", json.dumps(report), ex=STATUS_TTL)
    prev = local_status.get(request.sid)
    local_status[request.sid] = {"ms": report["reported_ms"], "health": report["health"],
                                 "drift_ms": report["drift_ms"] or 0}
    # only re-broadcast when something visible changed, so steady devices cost nothing
    if not prev or prev["health"] != report["health"] or \
            abs((report["drift_ms"] or 0) - prev["drift_ms"]) >= 15:
        dirty_rooms.add(info["room"])
    else:
        local_status[request.sid]["drift_ms"] = prev["drift_ms"]  # keep last broadcast value
    return {"ok": True, "health": report["health"]}


def socket_user_id():
    return (local_clients.get(request.sid) or {}).get("user_id")


@socketio.on("join")
def on_join(data):
    metrics["events"] += 1
    data = data or {}
    room_id = data.get("room_id")
    info = local_clients.get(request.sid)
    if not info or not info.get("user_id"):
        return {"error": "Log in to join a room."}
    if not membership(info["user_id"], room_id):
        return {"error": "Room not found."}
    leader_id = leader_of(room_id)
    state = live_state(leader_id) if leader_id else None
    if state is None:
        return {"error": "Room not found."}
    prev, prev_play = info.get("room"), info.get("play")
    if prev and prev != room_id:
        leave_room(prev)
        r.hdel(f"room:{prev}:members", request.sid)
        dirty_rooms.add(prev)
    if prev_play and prev_play != leader_id:
        leave_room(f"play:{prev_play}")
    join_room(room_id)
    join_room(f"play:{leader_id}")
    info["room"], info["play"] = room_id, leader_id
    save_client(request.sid, info)
    dirty_rooms.update({room_id, leader_id})
    items = queue_items(leader_id)
    return {
        "server": SERVER_ID,
        "room_id": room_id,
        "zone_id": leader_id,
        "zone_rooms": zone_room_ids(leader_id),
        "state": state,
        "queue": queue_payload(leader_id, items),
        "presence": presence_payload(leader_id),
    }


@socketio.on("leave")
def on_leave(_data=None):
    info = local_clients.get(request.sid)
    if not info or not info.get("room"):
        return {"ok": True}
    leave_room(info["room"])
    if info.get("play"):
        leave_room(f"play:{info['play']}")
    r.hdel(f"room:{info['room']}:members", request.sid)
    dirty_rooms.update({info["room"], info.get("play")} - {None})
    info["room"], info["play"] = None, None
    save_client(request.sid, info)
    return {"ok": True}


@socketio.on("command")
def on_command(data):
    metrics["events"] += 1
    data = data or {}
    action = data.get("action")
    info = local_clients.get(request.sid) or {}
    # you can only control the room this device is in, and only while you're a member
    if not info.get("user_id") or data.get("room_id") != info.get("room") or \
            not membership(info["user_id"], info.get("room")):
        return {"error": "Join the room first."}
    who = info.get("name", "someone")
    # a device in a linked room controls the whole zone, i.e. the leader's playback
    room_id = leader_of(info["room"])
    try:
        result = apply_command(room_id, action, data, who)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # keep the node alive on unexpected DB errors
        db.session.rollback()
        log("command failed:", repr(exc))
        return {"error": "Server error, try again"}
    if result is None:
        return {"ok": True, "ignored": True}
    payload, queue = result
    socketio.emit("state", payload, to=f"play:{room_id}")  # fans out to every node via Redis
    if queue is not None:
        socketio.emit("queue", queue, to=f"play:{room_id}")
    return {"ok": True, "version": payload["version"]}


@socketio.on("set_volumes")
def on_set_volumes(data):
    """{volumes: {room_id: 0-100}}. One message can set several rooms at once (the
    zone's master slider scales every linked room proportionally). Members only."""
    metrics["events"] += 1
    uid = socket_user_id()
    if not uid:
        return {"error": "Log in first."}
    volumes = (data or {}).get("volumes") or {}
    clean = {}
    try:
        for rid, v in list(volumes.items())[:50]:
            if not membership(uid, rid):
                continue
            room = db.session.get(Room, rid)
            room.volume = max(0, min(100, int(round(float(v)))))
            clean[rid] = room.volume
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log("set_volumes failed:", repr(exc))
        return {"error": "Could not change the volume"}
    if clean:
        notify_members(clean.keys(), "volumes", {"volumes": clean}, skip_sid=request.sid)
    return {"ok": True, "volumes": clean}


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def seed_rooms():
    """No rooms are created up front: people make their own. This only repairs rooms
    from older versions (missing playback row or invite code)."""
    have_state = {s.room_id for s in PlaybackState.query.all()}
    for room in Room.query.all():
        if room.id not in have_state:
            db.session.add(PlaybackState(room_id=room.id))
        if not room.code:
            room.code = new_room_code()
    db.session.commit()


def migrate():
    """Adds columns introduced after a table was first created (create_all never alters
    existing tables), so an old database keeps working without `docker compose down -v`."""
    from sqlalchemy import inspect

    insp = inspect(db.engine)
    with db.engine.begin() as conn:
        for model in (Track, Room):
            table = model.__table__
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(dialect=db.engine.dialect)
                default = ""
                if col.name == "volume":
                    default = " DEFAULT 70 NOT NULL"
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}{default}'))
                log(f"migrated: added {table.name}.{col.name}")


def init_node():
    """All nodes boot at once; a PostgreSQL advisory lock makes exactly one of them
    create tables / seed data at a time (a distributed mutex for initialization)."""
    for attempt in range(30):
        try:
            with app.app_context():
                is_pg = db.engine.dialect.name == "postgresql"
                with db.engine.connect() as lock_conn:
                    if is_pg:
                        lock_conn.execute(text("SELECT pg_advisory_lock(734201)"))
                    try:
                        db.create_all()
                        migrate()
                        fixed = library.normalize_uploads(db, Track, MEDIA_DIR)
                        if fixed:
                            log(f"converted {fixed} older upload(s) to CBR 192 kbps / 44.1 kHz MP3")
                        added = library.sync_library(db, Track, MEDIA_DIR)
                        pruned = prune_missing_uploads()
                        renamed = fix_raw_upload_names()
                        if renamed:
                            log(f"gave {renamed} upload(s) a readable title and artist")
                        if pruned:
                            log(f"removed {pruned} upload(s) whose file is missing")
                        seed_rooms()
                        log(f"database ready ({added} new tracks found)")
                    finally:
                        if is_pg:
                            lock_conn.execute(text("SELECT pg_advisory_unlock(734201)"))
                            lock_conn.commit()
            # forget sockets this node owned before a restart
            for sid, raw in r.hgetall("clients").items():
                if json.loads(raw).get("server") == SERVER_ID:
                    drop_client(sid, json.loads(raw))
            return
        except Exception as exc:
            log(f"waiting for database/redis ({exc.__class__.__name__}: {str(exc)[:300]}), attempt {attempt + 1}")
            time.sleep(2)
    raise SystemExit("could not initialize")


if __name__ == "__main__":
    init_node()
    socketio.start_background_task(heartbeat_loop)
    socketio.start_background_task(presence_loop)
    log(f"listening on :{PORT}")
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, log_output=False)
