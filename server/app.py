import os
import uuid
import json
import threading
import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, join_room, leave_room, emit
from models import db, Room, Track, PlaybackState
import redis as redis_lib

SERVER_ID = os.environ.get("SERVER_ID", "unknown")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///music.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret"

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", message_queue=REDIS_URL)

# Dedicated Redis connection for pub/sub subscription
_redis = redis_lib.from_url(REDIS_URL)
PUBSUB_CHANNEL = "room_events"


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"server": SERVER_ID, "status": "ok"})


@app.route("/api/rooms", methods=["GET"])
def list_rooms():
    rooms = Room.query.all()
    return jsonify([r.to_dict() for r in rooms])


@app.route("/api/rooms", methods=["POST"])
def create_room():
    data = request.get_json()
    room = Room(id=str(uuid.uuid4()), name=data["name"])
    state = PlaybackState(room_id=room.id)
    db.session.add(room)
    db.session.add(state)
    db.session.commit()
    return jsonify(room.to_dict()), 201


@app.route("/api/rooms/<room_id>", methods=["GET"])
def get_room(room_id):
    room = Room.query.get_or_404(room_id)
    state = PlaybackState.query.get(room_id)
    return jsonify({**room.to_dict(), "playback": state.to_dict() if state else None})


@app.route("/api/rooms/<room_id>/tracks", methods=["POST"])
def add_track(room_id):
    Room.query.get_or_404(room_id)
    data = request.get_json()
    track = Track(
        room_id=room_id,
        title=data["title"],
        artist=data.get("artist", ""),
        url=data.get("url", ""),
        position=data.get("position", 0),
    )
    db.session.add(track)
    db.session.commit()
    return jsonify(track.to_dict()), 201


# ---------------------------------------------------------------------------
# Socket.IO events (clients join/leave rooms, send playback commands)
# ---------------------------------------------------------------------------

@socketio.on("join")
def on_join(data):
    room_id = data["room_id"]
    join_room(room_id)
    emit("joined", {"room_id": room_id, "server": SERVER_ID})


@socketio.on("leave")
def on_leave(data):
    room_id = data["room_id"]
    leave_room(room_id)


@socketio.on("playback_command")
def on_playback_command(data):
    """
    Client sends: {"room_id": "...", "action": "play"|"pause"|"seek", "position": 0.0}
    This server persists state, then publishes to Redis so the other Flask instance
    can forward the event to its connected clients in the same room.
    """
    room_id = data["room_id"]
    action = data["action"]
    position = data.get("position", 0.0)

    # Persist to PostgreSQL
    state = PlaybackState.query.get(room_id)
    if state:
        if action == "play":
            state.is_playing = True
        elif action == "pause":
            state.is_playing = False
        state.position_seconds = position
        db.session.commit()

    # Broadcast to clients on THIS server in the room
    emit("playback_update", data, to=room_id)

    # Publish to Redis so OTHER Flask server(s) also broadcast to their clients
    _redis.publish(PUBSUB_CHANNEL, json.dumps({**data, "origin_server": SERVER_ID}))


# ---------------------------------------------------------------------------
# Redis subscriber — receives events published by the OTHER Flask server
# ---------------------------------------------------------------------------

def redis_listener():
    pubsub = _redis.pubsub()
    pubsub.subscribe(PUBSUB_CHANNEL)
    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        event = json.loads(message["data"])
        # Ignore events we ourselves published (we already emitted locally)
        if event.get("origin_server") == SERVER_ID:
            continue
        room_id = event["room_id"]
        # Push to our locally-connected clients in that room
        socketio.emit("playback_update", event, to=room_id)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def start_redis_listener():
    t = threading.Thread(target=redis_listener, daemon=True)
    t.start()


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    start_redis_listener()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
