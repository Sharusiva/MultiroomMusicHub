"""Scans the shared media folder and keeps the library table in sync with it."""
import json
import os
import random

AUDIO_EXT = {".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".opus"}
COVER_EXT = (".svg", ".jpg", ".jpeg", ".png", ".webp")
PALETTE = ["#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b", "#22c55e", "#3b82f6", "#ef4444", "#06b6d4"]
CODEC_BY_EXT = {".mp3": "MP3", ".m4a": "AAC", ".aac": "AAC", ".ogg": "Vorbis", ".opus": "Opus",
                ".wav": "WAV", ".flac": "FLAC"}


def read_tags(path):
    """Returns a dict with title, artist, duration, codec, bitrate, sample_rate, channels."""
    ext = os.path.splitext(path)[1].lower()
    out = {"title": None, "artist": None, "duration": 0.0, "codec": CODEC_BY_EXT.get(ext, ext[1:].upper()),
           "bitrate": None, "sample_rate": None, "channels": None}
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(path, easy=True)
        if mf is not None:
            info = getattr(mf, "info", None)
            if info is not None:
                out["duration"] = float(getattr(info, "length", 0) or 0)
                out["bitrate"] = int(getattr(info, "bitrate", 0) or 0) or None
                out["sample_rate"] = int(getattr(info, "sample_rate", 0) or 0) or None
                out["channels"] = int(getattr(info, "channels", 0) or 0) or None
                if ext in (".flac", ".wav") and out["sample_rate"] and not out["bitrate"]:
                    bits = getattr(info, "bits_per_sample", 16) or 16
                    out["bitrate"] = out["sample_rate"] * bits * (out["channels"] or 2)
            tags = mf.tags or {}
            out["title"] = (tags.get("title") or [None])[0]
            out["artist"] = (tags.get("artist") or [None])[0]
    except Exception:
        pass
    if not out["title"]:
        stem = os.path.splitext(os.path.basename(path))[0]
        out["title"] = stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled"
    out["artist"] = out["artist"] or "Unknown artist"
    return out


import re as _re

_PIXABAY_ID = _re.compile(r"[-_ ](\d{4,})$")


def guess_title_artist(filename, tags=None):
    """Best guess at (title, artist) for an upload whose file has no tags.
    Handles "Artist - Title.mp3", and Pixabay-style "artist-song-title-123456.mp3"
    (uploader name, then the title, then a numeric id)."""
    tags = tags or {}
    stem = os.path.splitext(os.path.basename(filename))[0].strip()
    t, a = (tags.get("title") or "").strip(), (tags.get("artist") or "").strip()
    raw_title = not t or t.lower().replace(" ", "") == stem.lower().replace(" ", "")
    if t and a and a != "Unknown artist" and not raw_title:
        return t, a
    if " - " in stem:  # "Burna Boy - Last Last"
        left, right = stem.split(" - ", 1)
        return right.strip(), (a if a and a != "Unknown artist" else left.strip())
    m = _PIXABAY_ID.search(stem)
    if m:
        words = [w for w in _re.split(r"[-_]+", stem[:m.start()]) if w]
        if len(words) >= 2:
            artist = a if a and a != "Unknown artist" else words[0]
            return " ".join(words[1:]).title(), artist
        stem = stem[:m.start()]
    nice = " ".join(w for w in _re.split(r"[-_]+", stem) if w).title() or "Untitled"
    return (t if t and not raw_title else nice), (a or "Unknown artist")


def looks_like_raw_filename(title):
    return bool(title) and " " not in title and bool(_PIXABAY_ID.search(title) or "-" in title or "_" in title)


# Every upload is re-encoded to the same format as the built-in library: constant
# bitrate MP3 at 44.1 kHz with an accurate seek table. Downloaded files are often
# variable-bitrate or 48 kHz, which Safari seeks inaccurately; the sync engine then
# keeps "correcting" and the song stutters or crackles.
NORMAL_BITRATE = 192000
NORMAL_RATE = 44100


def ffmpeg_available():
    from shutil import which
    return which("ffmpeg") is not None


def is_normalized(path, tags=None):
    tags = tags or read_tags(path)
    return (path.lower().endswith(".mp3") and tags.get("sample_rate") == NORMAL_RATE
            and tags.get("bitrate") == NORMAL_BITRATE)


def normalize_audio(src, dst):
    """Re-encode src to a CBR 192 kbps / 44.1 kHz stereo MP3 at dst. Returns True on success."""
    import subprocess
    tmp = dst + ".part.mp3"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-map", "0:a:0", "-vn",
           "-ar", str(NORMAL_RATE), "-ac", "2", "-codec:a", "libmp3lame", "-b:a", "192k",
           "-write_xing", "1", "-map_metadata", "0", "-id3v2_version", "3", tmp]
    try:
        subprocess.run(cmd, check=True, timeout=300, capture_output=True)
        os.replace(tmp, dst)
        return True
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def normalize_uploads(db, Track, media_dir):
    """Converts uploads saved by older versions (any format) to the normal format, once."""
    if not ffmpeg_available():
        return 0
    fixed = 0
    for track in Track.query.filter_by(uploaded=True).all():
        src = os.path.join(media_dir, track.filename)
        if not os.path.exists(src) or is_normalized(src):
            continue
        rel = os.path.splitext(track.filename)[0] + ".mp3"
        dst = os.path.join(media_dir, rel)
        if not normalize_audio(src, dst):
            continue
        if os.path.abspath(src) != os.path.abspath(dst):
            os.remove(src)
        tags = read_tags(dst)
        track.filename, track.codec, track.bitrate = rel, tags["codec"], tags["bitrate"]
        track.sample_rate, track.channels = tags["sample_rate"], tags["channels"]
        track.duration = tags["duration"] or track.duration
        fixed += 1
    db.session.commit()
    return fixed


def extract_embedded_cover(path, media_dir, stem):
    """Saves artwork embedded in an uploaded file (ID3 APIC, MP4 covr, FLAC picture). Returns rel path or None."""
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(path)
        if mf is None or mf.tags is None:
            return None
        data, mime = None, "image/jpeg"
        for key in list(mf.tags.keys()):
            if str(key).startswith("APIC"):
                data, mime = mf.tags[key].data, mf.tags[key].mime
                break
        if data is None and "covr" in mf.tags:
            data = bytes(mf.tags["covr"][0])
        if data is None and getattr(mf, "pictures", None):
            data, mime = mf.pictures[0].data, mf.pictures[0].mime
        if not data:
            return None
        ext = ".png" if "png" in (mime or "") else ".jpg"
        rel = f"covers/uploads/{stem}{ext}"
        os.makedirs(os.path.join(media_dir, "covers", "uploads"), exist_ok=True)
        with open(os.path.join(media_dir, rel), "wb") as f:
            f.write(data)
        return rel
    except Exception:
        return None


def find_cover(media_dir, rel_audio):
    """covers/<stem>.svg|jpg|png next to the library, if one exists."""
    stem = os.path.splitext(os.path.basename(rel_audio))[0]
    sub = "covers/uploads" if rel_audio.startswith("uploads") else "covers"
    for ext in COVER_EXT:
        rel = f"{sub}/{stem}{ext}"
        if os.path.exists(os.path.join(media_dir, rel)):
            return rel
    return None


def sync_library(db, Track, media_dir):
    """Adds audio files in media_dir (and media_dir/uploads) that aren't in the DB yet,
    and fills in signal-path details and covers for tracks that are missing them."""
    if not os.path.isdir(media_dir):
        return 0
    meta = {}
    meta_path = os.path.join(media_dir, "library.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = {m["file"]: m for m in json.load(f)}

    existing = {t.filename: t for t in Track.query.all()}
    candidates = []
    for sub in ("", "uploads"):
        folder = os.path.join(media_dir, sub)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if os.path.splitext(name)[1].lower() in AUDIO_EXT:
                candidates.append(os.path.join(sub, name) if sub else name)

    added = 0
    for rel in candidates:
        path = os.path.join(media_dir, rel)
        track = existing.get(rel)
        if track is not None:
            if track.sample_rate is None:  # created by an older version
                tags = read_tags(path)
                track.codec, track.bitrate = tags["codec"], tags["bitrate"]
                track.sample_rate, track.channels = tags["sample_rate"], tags["channels"]
            if not track.cover:
                track.cover = find_cover(media_dir, rel)
            continue
        tags = read_tags(path)
        m = meta.get(rel, {})
        db.session.add(Track(
            filename=rel,
            title=m.get("title", tags["title"]),
            artist=m.get("artist", tags["artist"]),
            genre=m.get("genre", ""),
            color=m.get("color", random.choice(PALETTE)),
            duration=tags["duration"],
            codec=tags["codec"],
            bitrate=tags["bitrate"],
            sample_rate=tags["sample_rate"],
            channels=tags["channels"],
            cover=find_cover(media_dir, rel),
            uploaded=rel.startswith("uploads"),
        ))
        added += 1
    db.session.commit()
    return added
