import { useState } from "react";
import { ArrowRight, LogOut, Plus, Users } from "lucide-react";
import { api, setToken } from "../net";
import Cover from "../ui/Cover";

const I = { strokeWidth: 1.5, "aria-hidden": true };

// The speaker-grille logo; its centre dot lights orange while music plays.
export function Grille({ on }) {
  return <span className={`grille ${on ? "on" : ""}`} aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} />)}</span>;
}

export const formatCode = (c) => (c ? `${c.slice(0, 3)} ${c.slice(3)}` : "");
export const cleanCode = (c) => c.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);

/** Log in or sign up. Both end with a session token the servers share through Redis. */
export function AuthScreen({ onAuthed, inviteCode }) {
  const [mode, setMode] = useState("signup");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api(`/auth/${mode}`, { method: "POST", json: { username, password } });
      setToken(res.token);
      onAuthed(res.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const signup = mode === "signup";
  return (
    <div className="join">
      <form className="join-panel" onSubmit={submit} noValidate>
        <Grille />
        <h1>{signup ? "Create your account" : "Welcome back"}</h1>
        <p>
          {inviteCode
            ? <>You've been invited to a listening room. {signup ? "Make an account" : "Log in"} to join it.</>
            : "Make private listening rooms, invite friends with a code, and play music in sync on every phone and laptop."}
        </p>
        <div className="seg" role="tablist" aria-label="Account">
          <button type="button" role="tab" aria-selected={signup} onClick={() => { setMode("signup"); setError(null); }}>Sign up</button>
          <button type="button" role="tab" aria-selected={!signup} onClick={() => { setMode("login"); setError(null); }}>Log in</button>
        </div>
        <label>
          Username
          <input className="field-input" value={username} autoComplete="username" autoCapitalize="none" spellCheck="false"
            onChange={(e) => setUsername(e.target.value)} required minLength={3} maxLength={32} />
        </label>
        <label>
          Password
          <input className="field-input" type="password" value={password}
            autoComplete={signup ? "new-password" : "current-password"}
            onChange={(e) => setPassword(e.target.value)} required minLength={signup ? 8 : 1} />
          {signup && <span className="hint">At least 8 characters.</span>}
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn solid" type="submit" disabled={busy || !username || !password}>
          {busy ? "One moment…" : signup ? "Create account" : "Log in"}
        </button>
      </form>
    </div>
  );
}

/** Home after logging in: your rooms, make a room, or join one with a code. */
export function Home({ user, rooms, loaded, onOpen, onCreate, onJoin, onLogout }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const run = async (what, fn) => {
    setError(null);
    setBusy(what);
    try { await fn(); } catch (err) { setError({ what, msg: err.message }); } finally { setBusy(null); }
  };

  return (
    <div className="home">
      <header className="home-top">
        <div className="brand"><Grille /><span>Multiroom</span></div>
        <span className="muted home-user">Signed in as <b>{user.display_name}</b></span>
        <button className="btn quiet" onClick={onLogout}><LogOut {...I} size={16} />Log out</button>
      </header>

      <div className="home-grid">
        <section className="home-rooms" aria-labelledby="your-rooms">
          <h1 id="your-rooms">Your rooms</h1>
          {loaded && !rooms.length && (
            <p className="home-empty"><span>You're not in any rooms yet. Create one and share its code, or enter a code someone sent you.</span></p>
          )}
          {rooms.length > 0 && <ul className="room-list">
            {rooms.map((room) => (
              <li key={room.id}>
                <button className="room-card" onClick={() => onOpen(room.id)}>
                  <Cover track={room} />
                  <span className="rc-text">
                    <b>{room.name}</b>
                    <small>
                      {room.now_playing
                        ? <><span className={`eq ${room.is_playing ? "" : "paused"}`} aria-hidden="true"><i /><i /><i /></span>{room.now_playing}</>
                        : "Nothing queued yet"}
                    </small>
                  </span>
                  <span className="rc-meta">
                    <span className="num">{formatCode(room.code)}</span>
                    <span className="muted"><Users {...I} size={14} /> <span className="num">{room.members}</span></span>
                  </span>
                  <ArrowRight {...I} size={18} className="rc-go" />
                </button>
              </li>
            ))}
          </ul>}
        </section>

        <aside className="home-actions">
          <form className="panel" onSubmit={(e) => { e.preventDefault(); if (name.trim()) run("create", () => onCreate(name.trim())); }}>
            <h2>Create a room</h2>
            <p>You'll get a code to invite others. Only people with the code can find it.</p>
            <div className="inline-form">
              <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
                placeholder="Room name, e.g. Friday Night" aria-label="Room name" />
              <button className="btn solid" type="submit" disabled={!name.trim() || busy === "create"}>
                <Plus {...I} size={16} />Create
              </button>
            </div>
            {error?.what === "create" && <p className="form-error" role="alert">{error.msg}</p>}
          </form>

          <form className="panel" onSubmit={(e) => { e.preventDefault(); if (code.length === 6) run("join", () => onJoin(code)); }}>
            <h2>Join with a code</h2>
            <p>Ask whoever made the room for its 6‑character code.</p>
            <div className="inline-form">
              <input className="field-input code-input num" value={formatCode(code)} inputMode="text" autoCapitalize="characters"
                autoComplete="off" spellCheck="false" placeholder="K7P 2QX" aria-label="Room code"
                onChange={(e) => setCode(cleanCode(e.target.value))} />
              <button className="btn solid" type="submit" disabled={code.length !== 6 || busy === "join"}>Join</button>
            </div>
            {error?.what === "join" && <p className="form-error" role="alert">{error.msg}</p>}
          </form>
        </aside>
      </div>
    </div>
  );
}
