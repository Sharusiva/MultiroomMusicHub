from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tracks = db.relationship("Track", backref="room", lazy=True)
    playback = db.relationship("PlaybackState", backref="room", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }


class Track(db.Model):
    __tablename__ = "tracks"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200))
    url = db.Column(db.String(500))  # stub: source URL or path
    position = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "url": self.url,
            "position": self.position,
        }


class PlaybackState(db.Model):
    __tablename__ = "playback_states"

    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), primary_key=True)
    is_playing = db.Column(db.Boolean, default=False)
    current_track_id = db.Column(db.Integer, db.ForeignKey("tracks.id"), nullable=True)
    position_seconds = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "room_id": self.room_id,
            "is_playing": self.is_playing,
            "current_track_id": self.current_track_id,
            "position_seconds": self.position_seconds,
        }
