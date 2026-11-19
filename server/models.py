from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Track(db.Model):
    """A song in the shared music library (the audio file itself lives in /media)."""
    __tablename__ = "library_tracks"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), unique=True, nullable=False)  # relative to MEDIA_DIR
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), default="Unknown artist")
    genre = db.Column(db.String(80), default="")
    color = db.Column(db.String(16), default="#8b5cf6")
    duration = db.Column(db.Float, default=0.0)
    uploaded = db.Column(db.Boolean, default=False)
    uploaded_by = db.Column(db.String(36), nullable=True)  # user id; null for built-ins and older uploads
    # signal-path details shown in the app's "signal path" view
    codec = db.Column(db.String(16), nullable=True)
    bitrate = db.Column(db.Integer, nullable=True)  # bits per second
    sample_rate = db.Column(db.Integer, nullable=True)  # Hz
    channels = db.Column(db.Integer, nullable=True)
    cover = db.Column(db.String(300), nullable=True)  # relative to MEDIA_DIR
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "genre": self.genre,
            "color": self.color,
            "duration": round(self.duration or 0, 2),
            "url": f"/media/{self.filename}",
            "file": self.filename.rsplit("/", 1)[-1],
            "cover": f"/media/{self.cover}" if self.cover else None,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "uploaded": self.uploaded,
            "uploaded_by": self.uploaded_by,
        }


class User(db.Model):
    """An account. Passwords are stored only as a salted scrypt hash."""
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)  # stored lowercase
    display_name = db.Column(db.String(40), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "username": self.username, "display_name": self.display_name}


class RoomMember(db.Model):
    """Who may see and control a room. You become a member by creating it or entering its code."""
    __tablename__ = "room_members"

    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), primary_key=True, index=True)
    role = db.Column(db.String(16), nullable=False, default="member")  # "owner" or "member"
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)


class Room(db.Model):
    """
    A private listening room, visible only to its members. Others join with its
    invite code. Rooms can be linked into a zone: a linked room follows its
    group_leader's playback (same song, same position), while keeping its own
    volume. group_leader is NULL for a room that plays on its own or leads a zone.
    """
    __tablename__ = "rooms"

    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(12), unique=True, nullable=True, index=True)  # invite code, e.g. K7P2QX
    owner_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    volume = db.Column(db.Integer, default=70, nullable=False)  # 0-100, shared by every device in the room
    group_leader = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "owner_id": self.owner_id,
            "volume": self.volume if self.volume is not None else 70,
            "group_leader": self.group_leader,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QueueItem(db.Model):
    """One entry in a room's play queue. Each room has its own queue."""
    __tablename__ = "queue_items"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), nullable=False, index=True)
    track_id = db.Column(db.Integer, db.ForeignKey("library_tracks.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    track = db.relationship("Track", lazy="joined")

    def to_dict(self):
        return {"id": self.id, "position": self.position, "track": self.track.to_dict()}


class PlaybackState(db.Model):
    """
    The authoritative playback state for one room.

    Position is not stored as a ticking number. Instead we store an anchor:
    "at server time anchor_ms the song was at `offset` seconds". Every device
    computes   position = offset + (server_now - anchor_ms) / 1000
    from its own synchronized clock, which keeps all speakers aligned without
    streaming the position constantly.

    `version` increases on every change, so devices can discard stale or
    out-of-order updates, and conditional commands (track_ended) are idempotent.
    """
    __tablename__ = "room_playback"

    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), primary_key=True)
    queue_index = db.Column(db.Integer, nullable=True)
    is_playing = db.Column(db.Boolean, default=False, nullable=False)
    offset = db.Column(db.Float, default=0.0, nullable=False)
    anchor_ms = db.Column(db.BigInteger, default=0, nullable=False)
    version = db.Column(db.Integer, default=0, nullable=False)
    last_action = db.Column(db.String(32), default="init")
    updated_by = db.Column(db.String(64), default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
