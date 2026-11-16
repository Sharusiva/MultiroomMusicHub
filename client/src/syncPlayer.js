// Plays the room's audio in lock-step with every other device.
//
// The server never streams "the position". It sends an anchor:
//     "at server time anchor_ms, the song is at `offset` seconds"
// Each device converts that to a position using its synchronized clock:
//     target = offset + (serverNow - anchor_ms) / 1000
//
// 1. Scheduled start: play/seek/next are stamped ~600 ms in the future, so all
//    devices start the song at the same instant even if the message reaches them
//    at different times.
// 2. Drift correction: every 250 ms we compare the real audio position with the
//    target. Small drift is corrected by nudging playbackRate (inaudible),
//    large drift with a hard seek.

const HARD_SEEK = 0.2; // seconds
const SOFT_ZONE = 0.02; // seconds; below this we consider the device in sync

function silentWavUrl() {
  const sr = 8000, n = 800;
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true);
  v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}

export class SyncPlayer {
  constructor(clock) {
    this.clock = clock;
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.state = null;
    this.loadedUrl = null;
    this.startTimer = null;
    this.drift = 0; // seconds, positive = this device is ahead
    this.blocked = false;
    this.onEnded = null; // (state) => void
    this.onStatus = null; // () => void
    this.endedReported = -1;
    this.audio.addEventListener("ended", () => this.reportEnded());
    this.timer = setInterval(() => this.tick(), 250);
  }

  // Must be called from a click/tap: browsers only allow audio after a user gesture.
  unlock() {
    const a = this.audio;
    a.src = silentWavUrl();
    this.loadedUrl = null;
    return a.play().then(() => a.pause()).catch(() => {}).finally(() => this.apply());
  }

  // v is the 0-1 fader position; audio taper so the fader feels even across its travel
  setVolume(v) {
    const pos = Math.max(0, Math.min(1, v));
    this.audio.volume = pos * pos;
  }

  setState(s) {
    if (!s) return;
    if (this.state && this.state.room_id === s.room_id && s.version < this.state.version) return; // stale
    this.state = s;
    this.apply();
  }

  clear() {
    this.state = null;
    clearTimeout(this.startTimer);
    this.audio.pause();
  }

  target() {
    const s = this.state;
    if (!s || !s.track) return null;
    if (!s.is_playing) return s.offset;
    return Math.max(0, s.offset + (this.clock.now() - s.anchor_ms) / 1000);
  }

  seekTo(t) {
    const a = this.audio;
    const set = () => {
      try { a.currentTime = Math.max(0, t); } catch { /* not seekable yet */ }
    };
    if (a.readyState >= 1) set();
    else a.addEventListener("loadedmetadata", () => {
      const tt = this.target();
      try { a.currentTime = Math.max(0, tt ?? t); } catch { /* ignore */ }
    }, { once: true });
  }

  play() {
    this.audio.play().then(() => {
      this.blocked = false;
      this.onStatus?.();
    }).catch(() => {
      this.blocked = true; // autoplay policy: needs a tap
      this.onStatus?.();
    });
  }

  apply() {
    const s = this.state;
    clearTimeout(this.startTimer);
    this.startTimer = null;
    if (!s || !s.track) {
      this.audio.pause();
      return;
    }
    if (this.loadedUrl !== s.track.url) {
      this.audio.src = s.track.url;
      this.loadedUrl = s.track.url;
      this.audio.load();
    }
    this.audio.playbackRate = 1;
    if (!s.is_playing) {
      this.audio.pause();
      this.seekTo(s.offset);
      return;
    }
    const wait = s.anchor_ms - this.clock.now();
    if (wait > 15) {
      // Scheduled start: get into position now, press play exactly at anchor time.
      this.audio.pause();
      this.seekTo(s.offset);
      this.startTimer = setTimeout(() => {
        this.startTimer = null;
        this.seekTo(this.target());
        this.play();
      }, wait);
    } else {
      this.seekTo(this.target());
      this.play();
    }
  }

  reportEnded() {
    const s = this.state;
    if (!s || this.endedReported === s.version) return;
    this.endedReported = s.version;
    this.onEnded?.(s);
  }

  tick() {
    const s = this.state;
    const a = this.audio;
    if (!s || !s.track || !s.is_playing || this.startTimer) {
      this.drift = 0;
      return;
    }
    const target = this.target();
    const dur = s.track.duration || a.duration || Infinity;
    if (target > dur + 0.3) return this.reportEnded(); // song finished (e.g. room was empty)
    if (a.paused) {
      if (!this.blocked && a.readyState >= 2) this.play();
      return;
    }
    if (a.readyState < 3 || a.seeking) return;
    const drift = a.currentTime - target;
    this.drift = drift;
    if (Math.abs(drift) > HARD_SEEK) {
      a.playbackRate = 1;
      a.currentTime = target + 0.05; // seeking itself takes a moment
    } else if (Math.abs(drift) > SOFT_ZONE) {
      a.playbackRate = Math.min(1.05, Math.max(0.95, 1 - drift * 0.8));
    } else if (a.playbackRate !== 1) {
      a.playbackRate = 1;
    }
  }
}
