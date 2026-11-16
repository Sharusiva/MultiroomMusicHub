import { useRef, useState } from "react";
import { Pause, Play, SkipBack, SkipForward, Speaker } from "lucide-react";
import Cover from "../ui/Cover";
import Fader from "../ui/Fader";

export const fmt = (s) => {
  if (s == null || !isFinite(s)) return "0:00";
  s = Math.max(0, Math.floor(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const I = { size: 20, strokeWidth: 1.5, "aria-hidden": true };

function SeekBar({ position, duration, playing, onSeek }) {
  const [drag, setDrag] = useState(null); // fraction while dragging
  const ref = useRef(null);
  const frac = drag ?? (duration ? Math.min(1, position / duration) : 0);

  const at = (e) => {
    const rect = ref.current.getBoundingClientRect();
    return Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
  };
  const down = (e) => {
    if (!duration) return;
    ref.current.setPointerCapture(e.pointerId);
    setDrag(at(e));
  };
  const move = (e) => drag != null && setDrag(at(e));
  const up = (e) => {
    if (drag == null) return;
    onSeek(at(e) * duration);
    setDrag(null);
  };
  const key = (e) => {
    if (!duration) return;
    const step = e.shiftKey ? 15 : 5;
    if (e.key === "ArrowRight") { e.preventDefault(); onSeek(Math.min(duration, position + step)); }
    if (e.key === "ArrowLeft") { e.preventDefault(); onSeek(Math.max(0, position - step)); }
  };

  return (
    <div className="scrub">
      <span className="num">{fmt(drag != null ? drag * duration : position)}</span>
      <div
        ref={ref}
        className={`bar ${playing ? "on" : ""}`}
        role="slider"
        tabIndex={0}
        aria-label="Song position"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration || 0)}
        aria-valuenow={Math.round(position)}
        aria-valuetext={`${fmt(position)} of ${fmt(duration)}`}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={() => setDrag(null)}
        onKeyDown={key}
      >
        <div className="bar-fill" style={{ width: `${frac * 100}%` }} />
        <div className="bar-knob" style={{ left: `${frac * 100}%` }} />
      </div>
      <span className="num">{fmt(duration)}</span>
    </div>
  );
}

export default function Transport({ track, position, playing, canPlay, onToggle, onPrev, onNext, onSeek,
  zoneLabel, zoneSynced, onOpenZones, myRoom, onVolume, onVolumeCommit }) {
  const duration = track?.duration || 0;
  const frac = duration ? Math.min(1, position / duration) : 0;
  return (
    <footer className="transport" aria-label="Playback controls">
      <div className={`t-mobile-bar ${playing ? "on" : ""}`} aria-hidden="true">
        <div style={{ width: `${frac * 100}%` }} />
      </div>
      <div className="t-track">
        <Cover track={track} />
        <div className="t-meta">
          <div className="t-title">{track?.title || "Nothing playing"}</div>
          <div className="t-artist">{track ? track.artist : "Add a song from the library"}</div>
        </div>
      </div>

      <div className="t-center">
        <div className="keys">
          <button className="key" onClick={onPrev} disabled={!track} aria-label="Previous song"><SkipBack {...I} size={18} /></button>
          <button className={`key play ${playing ? "on" : ""}`} onClick={onToggle} disabled={!canPlay}
            aria-label={playing ? "Pause" : "Play"}>
            {playing ? <Pause {...I} size={22} /> : <Play {...I} size={22} style={{ marginLeft: 3 }} />}
          </button>
          <button className="key" onClick={onNext} disabled={!track} aria-label="Next song"><SkipForward {...I} size={18} /></button>
        </div>
        <SeekBar position={position} duration={duration} playing={playing} onSeek={onSeek} />
      </div>

      <div className="t-right">
        <button className="zone-btn" onClick={onOpenZones} aria-label={`Zones: ${zoneLabel}`}>
          <Speaker {...I} size={18} />
          <span>{zoneLabel}</span>
          {zoneSynced && <i className="sync" aria-hidden="true" />}
        </button>
        {myRoom && (
          <Fader value={myRoom.volume} onChange={onVolume} onCommit={onVolumeCommit}
            label={`${myRoom.name} volume`} />
        )}
      </div>
    </footer>
  );
}
