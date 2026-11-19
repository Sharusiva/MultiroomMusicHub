import { useEffect, useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { Cast, MoreHorizontal, Plus, Trash2, Upload, X } from "lucide-react";
import Cover from "../ui/Cover";
import { fmt } from "./Transport";

const I = { strokeWidth: 1.5, "aria-hidden": true };

/** Assign a song to one of your other rooms without leaving this one. */
function SendToRoom({ track, rooms, onSend }) {
  const [open, setOpen] = useState(false);
  const send = (room, play) => { onSend(track, room, play); setOpen(false); };
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button className="icon-btn" style={{ opacity: 1 }} aria-label={`Send ${track.title} to another room`}
          title="Send to another room">
          <Cast {...I} size={17} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover send-menu" align="end" sideOffset={6} collisionPadding={16}>
          <h3>Send to another room</h3>
          <p>{track.title}</p>
          {rooms.map((room) => (
            <div className="send-row" key={room.id}>
              <div>
                <b>{room.name}</b>
                <small>{room.now_playing ? `${room.is_playing ? "Playing" : "Paused"}: ${room.now_playing}` : "Nothing queued"}</small>
              </div>
              <button className="btn" onClick={() => send(room, false)}>Queue</button>
              <button className="btn solid" onClick={() => send(room, true)}>Play</button>
            </div>
          ))}
          {!rooms.length && <p className="send-empty">You have no other rooms yet. Make one from the rooms drawer.</p>}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** "⋯" menu on songs you uploaded: fix the title/artist, or delete (two taps). */
function SongMenu({ track, onEdit, onDelete }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(track.title);
  const [artist, setArtist] = useState(track.artist);
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (open) { setTitle(track.title); setArtist(track.artist); setArmed(false); }
  }, [open, track.title, track.artist]);
  const save = (e) => {
    e.preventDefault();
    onEdit(track, { title: title.trim(), artist: artist.trim() });
    setOpen(false);
  };
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button className="icon-btn" style={{ opacity: 1 }} aria-label={`Edit or delete ${track.title}`} title="Edit or delete">
          <MoreHorizontal {...I} size={17} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover song-menu" align="end" sideOffset={6} collisionPadding={16}>
          <h3>Song details</h3>
          <form onSubmit={save}>
            <label>Title<input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} required /></label>
            <label>Artist<input value={artist} maxLength={200} onChange={(e) => setArtist(e.target.value)} /></label>
            <div className="song-menu-actions">
              <button type="button" className={`btn ${armed ? "solid danger-btn" : "quiet"}`}
                onClick={() => (armed ? (onDelete(track), setOpen(false)) : setArmed(true))}>
                <Trash2 {...I} size={15} />{armed ? "Tap again to delete" : "Delete song"}
              </button>
              <span className="grow" />
              <button type="submit" className="btn solid" disabled={!title.trim()}>Save</button>
            </div>
          </form>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export default function Queue({ queue, library, current, playing, onJump, onRemove, onAdd, onClear, onUpload, uploading,
  otherRooms = [], onSend, userId, onDeleteTrack, onEditTrack }) {
  const [tab, setTab] = useState("queue");
  const fileRef = useRef(null);
  return (
    <aside className="side" aria-label="Queue and library">
      <div className="side-head">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "queue"} onClick={() => setTab("queue")}>
            Up next <span className="num muted">{queue.length}</span>
          </button>
          <button role="tab" aria-selected={tab === "library"} onClick={() => setTab("library")}>
            Library <span className="num muted">{library.length}</span>
          </button>
        </div>
        <span className="grow" />
        {tab === "queue" && queue.length > 0 && <button className="btn quiet" onClick={onClear}>Clear</button>}
        {tab === "library" && (
          <>
            <button className="btn" disabled={uploading} onClick={() => fileRef.current?.click()}>
              <Upload {...I} size={16} />{uploading ? "Uploading…" : "Upload"}
            </button>
            <input ref={fileRef} type="file" accept="audio/*" multiple hidden onChange={onUpload} />
          </>
        )}
      </div>

      {tab === "queue" ? (
        <ol className="list" role="tabpanel" aria-label="Up next">
          {queue.map((item, i) => {
            const isCur = i === current;
            return (
              <li key={item.id} className={`row ${isCur ? "current" : ""}`}>
                <span className="idx num">
                  {isCur ? <span className={`eq ${playing ? "" : "paused"}`} aria-label={playing ? "Playing" : "Paused"}><i /><i /><i /></span>
                    : String(i + 1).padStart(2, "0")}
                </span>
                <Cover track={item.track} />
                <button className="row-text" onClick={() => onJump(i)} aria-label={`Play ${item.track.title}`}>
                  <b>{item.track.title}</b><small>{item.track.artist}</small>
                </button>
                <span className="dur num">{fmt(item.track.duration)}</span>
                <button className="icon-btn" aria-label={`Remove ${item.track.title} from the queue`} onClick={() => onRemove(item.id)}>
                  <X {...I} size={16} />
                </button>
              </li>
            );
          })}
          {!queue.length && <li className="empty">The queue is empty. Add songs from Library.</li>}
        </ol>
      ) : (
        <ul className="list" role="tabpanel" aria-label="Library">
          {library.map((t) => (
            <li key={t.id} className="row" style={{ gridTemplateColumns: "0 40px minmax(0,1fr) auto 32px 32px 32px" }}>
              <span />
              <Cover track={t} />
              <div className="row-text"><b>{t.title}</b><small>{t.artist}{t.genre ? `, ${t.genre}` : ""}</small></div>
              <span className="dur num">{fmt(t.duration)}</span>
              {t.uploaded && (!t.uploaded_by || t.uploaded_by === userId)
                ? <SongMenu track={t} onEdit={onEditTrack} onDelete={onDeleteTrack} /> : <span />}
              <SendToRoom track={t} rooms={otherRooms} onSend={onSend} />
              <button className="icon-btn" style={{ opacity: 1 }} aria-label={`Add ${t.title} to the queue`} onClick={() => onAdd(t)}>
                <Plus {...I} size={18} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
