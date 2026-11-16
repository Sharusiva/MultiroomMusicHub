import { AnimatePresence, motion } from "motion/react";
import Cover from "../ui/Cover";
import SignalPath from "./SignalPath";

export default function Stage({ track, roomState, core, conn, zoneLabel, zoneRooms, presence, leadMs, health, linked }) {
  const devices = presence?.devices || [];
  const deviceCount = devices.length + (presence?.virtual || 0);
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
        <h2 className="section-title">Speakers in this zone</h2>
        <ul className="speaker-list">
          {devices.map((d) => {
            const me = d.sid === core.socket?.id;
            return (
              <li key={d.sid} className={`speaker ${me ? "me" : ""}`}>
                <span>{d.name}{me ? " (you)" : ""}</span>
                {zoneRooms > 1 && <span className="where">{d.room}</span>}
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
