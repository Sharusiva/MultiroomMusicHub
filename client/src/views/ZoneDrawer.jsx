import { useEffect, useMemo, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { DoorOpen, Link2, Plus, Smartphone, Trash2, Unlink2, X } from "lucide-react";
import Fader from "../ui/Fader";
import { cleanCode, formatCode } from "./Lobby";

const I = { strokeWidth: 1.5, "aria-hidden": true };
// One spring for everything that moves when zones change, so merges feel like one physical system.
export const SPRING = { type: "spring", stiffness: 420, damping: 36, mass: 0.9 };

function useIsPhone() {
  const q = "(max-width: 760px)";
  const [m, setM] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return m;
}

export function groupRooms(rooms, zoneId) {
  const ids = new Set(rooms.map((r) => r.id));
  const map = new Map();
  rooms.forEach((r) => {
    const leader = r.group_leader && ids.has(r.group_leader) ? r.group_leader : r.id;
    if (!map.has(leader)) map.set(leader, []);
    map.get(leader).push(r);
  });
  const order = (id) => rooms.findIndex((r) => r.id === id);
  return [...map.entries()]
    .map(([leader, members]) => ({
      leader,
      rooms: members.sort((a, b) => (a.id === leader ? -1 : b.id === leader ? 1 : order(a.id) - order(b.id))),
    }))
    .sort((a, b) => (a.leader === zoneId ? -1 : b.leader === zoneId ? 1 : order(a.leader) - order(b.leader)));
}

export function zoneName(group) {
  if (!group) return "";
  if (group.rooms.length === 1) return group.rooms[0].name;
  if (group.rooms.length === 2) return `${group.rooms[0].name} + ${group.rooms[1].name}`;
  return `${group.rooms[0].name} + ${group.rooms.length - 1} rooms`;
}

function NowPlaying({ room }) {
  if (!room.now_playing) return <small>Nothing queued</small>;
  return (
    <small>
      <span className={`eq ${room.is_playing ? "" : "paused"}`} aria-hidden="true"><i /><i /><i /></span>
      <span className="sr-only">{room.is_playing ? "Playing" : "Paused"}:</span>
      {room.now_playing}
    </small>
  );
}

function RoomRow({ room, group, isMine, inMyZone, onMove, onLink, onUnlink, onDelete, onLeave, onVolume, onVolumeCommit }) {
  const [confirm, setConfirm] = useState(false);
  const linked = group.rooms.length > 1;
  const isSource = linked && room.id === group.leader;
  useEffect(() => {
    if (!confirm) return;
    const t = setTimeout(() => setConfirm(false), 3000);
    return () => clearTimeout(t);
  }, [confirm]);

  let toggle = null;
  if (linked && !isSource) {
    toggle = (
      <button className="link-toggle" aria-pressed="true" onClick={() => onUnlink(room.id)}
        title={`Stop playing ${zoneName(group)} in ${room.name}`}>
        <Link2 {...I} size={16} /> Linked
      </button>
    );
  } else if (!inMyZone) {
    toggle = (
      <button className="link-toggle" aria-pressed="false" onClick={() => onLink(room.id)}
        title={`Play what you're hearing in ${room.name} too`}>
        <Unlink2 {...I} size={16} /> Link
      </button>
    );
  }

  return (
    <motion.div layout="position" layoutId={`room-${room.id}`} transition={SPRING} className="zone-room">
      <div className="zr-top">
        {isMine ? (
          <div className="zr-name">
            <b>{room.name} <span className="zr-code num">{formatCode(room.code)}</span></b>
            <NowPlaying room={room} />
          </div>
        ) : (
          <button className="zr-name" onClick={() => onMove(room.id)} title={`Move this device to ${room.name}`}>
            <b>{room.name} <span className="zr-code num">{formatCode(room.code)}</span></b>
            <NowPlaying room={room} />
          </button>
        )}
        <div className="zr-actions">
          <span className="zr-count num" title="Devices in this room">
            <Smartphone {...I} size={14} />{room.devices}
          </span>
          {isMine && <span className="zr-here">This device</span>}
          {isSource && !isMine && <span className="zr-here" style={{ borderColor: "var(--hair)" }}>Source</span>}
          {toggle}
          {!linked && !isMine && (
            confirm ? (
              <button className="link-toggle danger-confirm"
                onClick={() => (room.role === "owner" ? onDelete(room.id) : onLeave(room.id))}>
                {room.role === "owner" ? "Delete room" : "Leave room"}
              </button>
            ) : (
              <button className="icon-btn" style={{ width: 32, height: 32 }}
                aria-label={room.role === "owner" ? `Delete ${room.name}` : `Leave ${room.name}`}
                title={room.role === "owner" ? "Delete this room for everyone" : "Leave this room"}
                onClick={() => setConfirm(true)}>
                {room.role === "owner" ? <Trash2 {...I} size={16} /> : <DoorOpen {...I} size={16} />}
              </button>
            )
          )}
        </div>
      </div>
      <Fader value={room.volume} label={`${room.name} volume`}
        onChange={(v) => onVolume({ [room.id]: v })} onCommit={(v) => onVolumeCommit({ [room.id]: v })} />
    </motion.div>
  );
}

function ZoneCard({ group, zoneId, roomId, handlers }) {
  const linked = group.rooms.length > 1;
  const snap = useRef(null);
  const master = Math.max(...group.rooms.map((r) => r.volume));
  const playing = group.rooms[0].is_playing;

  // Master fader: scales every linked room proportionally from where they were when
  // the drag started, so a 40/80 balance stays 1:2 as you turn the zone down.
  const scaled = (v) => {
    if (!snap.current) snap.current = { max: master, vols: Object.fromEntries(group.rooms.map((r) => [r.id, r.volume])) };
    const { max, vols } = snap.current;
    return Object.fromEntries(Object.entries(vols).map(([id, vol]) => [
      id, max === 0 ? v : Math.max(0, Math.min(100, Math.round((vol * v) / max))),
    ]));
  };

  return (
    <motion.section layout transition={SPRING} className={`zone ${linked ? "linked" : ""}`}
      aria-label={linked ? `Zone: ${zoneName(group)}` : group.rooms[0].name}>
      <AnimatePresence initial={false}>
        {linked && (
          <motion.div className="zone-head" layout="position" transition={SPRING}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="zone-head-top">
              <i className="sync" aria-hidden="true" />
              <span>{group.rooms.length} rooms in sync</span>
              <span className="muted">{playing ? "playing" : "paused"}</span>
              <button className="btn" onClick={() => handlers.onUnlink(group.leader)}>Split zone</button>
            </div>
            <span className="fader-label">Zone volume</span>
            <Fader size="lg" value={master} label={`${zoneName(group)} zone volume`}
              onChange={(v) => handlers.onVolume(scaled(v))}
              onCommit={(v) => { handlers.onVolumeCommit(scaled(v)); snap.current = null; }} />
          </motion.div>
        )}
      </AnimatePresence>
      {group.rooms.map((room) => (
        <RoomRow key={room.id} room={room} group={group} isMine={room.id === roomId}
          inMyZone={group.leader === zoneId} {...handlers} />
      ))}
    </motion.section>
  );
}

export default function ZoneDrawer({ open, onOpenChange, rooms, roomId, zoneId, user, handlers, onCreate, onJoin }) {
  const phone = useIsPhone();
  const groups = useMemo(() => groupRooms(rooms, zoneId), [rooms, zoneId]);
  const [newRoom, setNewRoom] = useState("");
  const [code, setCode] = useState("");
  const [footError, setFootError] = useState(null);
  const attempt = async (fn) => {
    setFootError(null);
    try { await fn(); } catch (e) { setFootError(e.message); }
  };
  const slide = phone ? { y: "100%" } : { x: "100%" };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </Dialog.Overlay>
            <Dialog.Content asChild forceMount>
              <motion.div className="drawer" initial={slide} animate={{ x: 0, y: 0 }} exit={slide}
                transition={{ type: "spring", stiffness: 380, damping: 40 }}>
                <div className="drawer-head">
                  <div>
                    <Dialog.Title asChild><h2>Your rooms</h2></Dialog.Title>
                    <Dialog.Description asChild>
                      <p>Only rooms you've made or joined. Link two to play the same song in sync, or tap one to switch this device to it.</p>
                    </Dialog.Description>
                  </div>
                  <Dialog.Close asChild>
                    <button className="icon-btn" aria-label="Close zones"><X {...I} size={20} /></button>
                  </Dialog.Close>
                </div>

                <div className="drawer-body">
                  <div className="me-card">
                    <Smartphone {...I} size={16} />
                    <span>Signed in as <b>{user.display_name}</b></span>
                  </div>
                  <LayoutGroup>
                    {groups.map((g) => (
                      <ZoneCard key={g.leader} group={g} zoneId={zoneId} roomId={roomId} handlers={handlers} />
                    ))}
                  </LayoutGroup>
                </div>

                <div className="drawer-foot">
                  <form className="new-room" onSubmit={(e) => {
                    e.preventDefault();
                    if (!newRoom.trim()) return;
                    attempt(async () => { await onCreate(newRoom.trim()); setNewRoom(""); });
                  }}>
                    <input className="field-input" value={newRoom} onChange={(e) => setNewRoom(e.target.value)}
                      placeholder="New room, e.g. Road Trip" aria-label="New room name" maxLength={60} />
                    <button className="btn solid" type="submit"><Plus {...I} size={16} />Create</button>
                  </form>
                  <form className="new-room" onSubmit={(e) => {
                    e.preventDefault();
                    if (code.length !== 6) return;
                    attempt(async () => { await onJoin(code); setCode(""); });
                  }}>
                    <input className="field-input num" value={formatCode(code)} onChange={(e) => setCode(cleanCode(e.target.value))}
                      placeholder="Room code, e.g. K7P 2QX" aria-label="Room code" autoCapitalize="characters" autoComplete="off" />
                    <button className="btn" type="submit" disabled={code.length !== 6}>Join</button>
                  </form>
                  {footError && <p className="form-error" role="alert">{footError}</p>}
                </div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
