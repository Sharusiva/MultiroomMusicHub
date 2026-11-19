import { AnimatePresence, motion } from "motion/react";
import Cover from "../ui/Cover";
import SignalPath from "./SignalPath";

// How each room node's latest status report is shown. "bad" ones count as needing attention.
const HEALTH = {
  in_sync: { led: "ok", label: (s) => `in sync${s?.drift_ms != null ? ` · ${Math.abs(s.drift_ms).toFixed(0)} ms` : ""}` },
  correcting: { led: "warn", label: (s) => `catching up · ${Math.abs(s.drift_ms).toFixed(0)} ms` },
  out_of_sync: { led: "bad", label: (s) => `out of sync · ${Math.abs(s.drift_ms).toFixed(0)} ms` },
  buffering: { led: "warn", label: () => "buffering" },
  blocked: { led: "bad", label: () => "needs a tap" },
  idle: { led: "", label: (s) => (s?.state === "paused" ? "paused" : "ready") },
  silent: { led: "bad", label: () => "not responding" },
};

function speakerSummary(devices) {
  if (!devices.length) return null;
  const bad = devices.filter((d) => HEALTH[d.health]?.led === "bad").length;
  const playing = devices.filter((d) => d.health === "in_sync").length;
  if (bad) return `${bad} of ${devices.length} need${bad === 1 ? "s" : ""} attention`;
  if (playing === devices.length) return devices.length === 1 ? "playing in sync" : `all ${devices.length} in sync`;
  return `${devices.length} speaker${devices.length === 1 ? "" : "s"}`;
}

export default function Stage({ track, roomState, core, conn, zoneLabel, zoneRooms, presence, leadMs, health, linked }) {
  const devices = presence?.devices || [];
  const deviceCount = devices.length + (presence?.virtual || 0);
  const summary = speakerSummary(devices);
  return (
    <section className="stage" aria-label="Now playing">
      <div className="stage-grid">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={track?.id ?? "none"} initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.985 }} transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }}>
            <Cover track={track} alt={track ? `Cover of ${track.title}` : ""} />
          </motion.div>
        </AnimatePresence>
        <div className="np">
          <div className="np-where">
            {linked && <i className="sync" aria-hidden="true" />}
            <span>{linked ? "In sync across" : "Playing in"} <b>{zoneLabel || "…"}</b></span>
          </div>
          <h1 className="np-title">{track?.title || "Nothing playing yet"}</h1>
          <p className="np-artist">{track ? track.artist : "Open Library and add a song to start this room."}</p>
          <SignalPath track={track} state={roomState} core={core} server={conn.server} zoneLabel={zoneLabel}
            zoneRooms={zoneRooms} deviceCount={deviceCount} leadMs={leadMs} health={health} />
        </div>
      </div>

      <div className="speakers">
        <h2 className="section-title">
          Speakers in this zone{summary && <span className="speaker-summary"> · {summary}</span>}
        </h2>
        <ul className="speaker-list">
          {devices.map((d) => {
            const me = d.sid === core.socket?.id;
            const h = HEALTH[d.health] || HEALTH.idle;
            const st = d.status;
            const tip = st
              ? `Reported ${st.state}${st.drift_ms != null ? `, ${st.drift_ms} ms drift` : ""}, via ${st.server}`
              : "No status report in the last few seconds";
            return (
              <li key={d.sid} className={`speaker ${me ? "me" : ""} ${h.led === "bad" ? "alert" : ""}`}>
                <i className={`led ${h.led}`} aria-hidden="true" />
                <span>{d.name}{me ? " (you)" : ""}</span>
                {zoneRooms > 1 && <span className="where">{d.room}</span>}
                <span className="health" title={tip}>{h.label(st)}</span>
                <span className="num" title="Server this device is connected to">{d.server}</span>
              </li>
            );
          })}
          {presence?.virtual > 0 && <li className="speaker"><span className="num">+{presence.virtual}</span> virtual listeners</li>}
          {!devices.length && <li className="muted">Connecting…</li>}
        </ul>
      </div>
    </section>
  );
}
