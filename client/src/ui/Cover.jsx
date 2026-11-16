import { useState } from "react";

// Album art. Falls back to the track's color with its initials when a track has
// no cover (e.g. an upload without embedded artwork).
export default function Cover({ track, className = "", alt = "" }) {
  const [broken, setBroken] = useState(false);
  const src = track?.cover || track?.now_playing_cover;
  if (src && !broken) {
    return (
      <div className={`cover ${className}`}>
        <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setBroken(true)} />
      </div>
    );
  }
  const initials = (track?.title || track?.now_playing || "").split(/\s+/).map((w) => w[0]).join("").slice(0, 2);
  return (
    <div className={`cover ${className}`} style={{ background: track?.color || "var(--stone-deep)" }} aria-hidden={!alt}>
      <span className="cover-fallback" style={{ fontSize: "38%" }}>{initials}</span>
    </div>
  );
}
