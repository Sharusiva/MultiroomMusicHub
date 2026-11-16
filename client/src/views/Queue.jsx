import { useRef, useState } from "react";
import { Plus, Upload, X } from "lucide-react";
import Cover from "../ui/Cover";
import { fmt } from "./Transport";

const I = { strokeWidth: 1.5, "aria-hidden": true };

export default function Queue({ queue, library, current, playing, onJump, onRemove, onAdd, onClear, onUpload, uploading }) {
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
            <li key={t.id} className="row" style={{ gridTemplateColumns: "0 40px minmax(0,1fr) auto 32px" }}>
              <span />
              <Cover track={t} />
              <div className="row-text"><b>{t.title}</b><small>{t.artist}{t.genre ? `, ${t.genre}` : ""}</small></div>
              <span className="dur num">{fmt(t.duration)}</span>
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
