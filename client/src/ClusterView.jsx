import { useEffect, useState } from "react";
import { api, fleet, onServed, servedLog } from "./net";

// Servers are told apart by line pattern and shade, not color: orange is reserved for playback.
const DASH = ["", "7 5", "2 4", "10 3 2 3"];
const STROKE = ["#1F1E1B", "#1F1E1B", "#6B6860", "#6B6860"];
const idx = (id, ids) => Math.max(0, ids.indexOf(id));

const history = []; // survives switching views
const HISTORY_LEN = 90;

function Chart({ ids }) {
  const W = 640, H = 200, P = 30;
  const max = Math.max(4, ...history.flatMap((h) => ids.map((id) => h.nodes[id] ?? 0)));
  const x = (i) => P + (i / (HISTORY_LEN - 1)) * (W - P - 8);
  const y = (v) => H - P + 4 - (v / max) * (H - P - 14);
  const offset = HISTORY_LEN - history.length;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Open connections per server over the last 90 seconds">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={P} x2={W - 8} y1={y(max * f)} y2={y(max * f)} className="grid" />
          <text x={P - 8} y={y(max * f) + 4} className="axis" textAnchor="end">{Math.round(max * f)}</text>
        </g>
      ))}
      {ids.map((id) => {
        const pts = history.map((h, i) => `${x(i + offset)},${y(h.nodes[id] ?? 0)}`).join(" ");
        const k = idx(id, ids);
        return pts && <polyline key={id} points={pts} fill="none" stroke={STROKE[k % 4]} strokeDasharray={DASH[k % 4]}
          strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />;
      })}
      <text x={W - 8} y={H - 6} className="axis" textAnchor="end">now</text>
      <text x={P} y={H - 6} className="axis">90 s ago</text>
    </svg>
  );
}

function Swatch({ k }) {
  return (
    <svg width="22" height="6" aria-hidden="true">
      <line x1="1" x2="21" y1="3" y2="3" stroke={STROKE[k % 4]} strokeDasharray={DASH[k % 4]} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function ClusterView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [, force] = useState(0);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const d = await api("/cluster");
        if (!alive) return;
        setData(d);
        setError(null);
        history.push({ t: Date.now(), nodes: Object.fromEntries(d.nodes.map((n) => [n.id, n.alive ? n.connections : 0])) });
        if (history.length > HISTORY_LEN) history.shift();
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    poll();
    const t = setInterval(poll, 1000);
    const u1 = fleet.subscribe(() => force((v) => v + 1));
    const u2 = onServed(() => force((v) => v + 1));
    return () => { alive = false; clearInterval(t); u1(); u2(); };
  }, []);

  const nodes = data?.nodes || [];
  const ids = nodes.map((n) => n.id);
  const total = data?.total_connections || 0;
  const aliveCount = nodes.filter((n) => n.alive).length;
  const fleetPer = fleet.perServer();
  const recent = servedLog.filter((s) => s.path === "/cluster").slice(-18);
  const events = nodes.reduce((a, n) => a + (n.alive ? n.events_per_sec || 0 : 0), 0);

  return (
    <div className="cluster">
      <div className="cl-head">
        <h1>Cluster</h1>
        <p>Three identical servers share the work behind NGINX. Add listeners to load them, stop one to watch its devices move to the others.</p>
      </div>

      <section className="stats" aria-label="Cluster totals">
        <div className="stat"><b>{total}</b><span>open connections</span></div>
        <div className="stat"><b>{aliveCount}/{nodes.length || 3}</b><span>servers up</span></div>
        <div className="stat"><b>{Math.round(events)}</b><span>messages per second</span></div>
        <div className="stat"><b>{fleet.connectedCount()}</b><span>virtual listeners from this browser</span></div>
      </section>
      {error && <div className="banner">Couldn't reach the cluster: {error}. Retrying every second.</div>}

      <section className="nodes" aria-label="Servers">
        {nodes.map((n) => {
          const share = total && n.alive ? (n.connections / total) * 100 : 0;
          return (
            <div key={n.id} className={`node-card ${n.alive ? "" : "down"}`}>
              <div className="nc-top">
                <span className="num">{n.id}</span>
                <span className="nc-state"><i aria-hidden="true" />{n.alive ? "up" : "down"}</span>
              </div>
              <div className="nc-big">{n.alive ? n.connections : "–"}<small>connections</small></div>
              <div className="share" aria-hidden="true"><div style={{ width: `${share}%` }} /></div>
              <dl className="nc-stats">
                <div><dt>Devices</dt><dd className="num">{n.alive ? n.devices : "–"}</dd></div>
                <div><dt>Virtual</dt><dd className="num">{n.alive ? n.virtual : "–"}</dd></div>
                <div><dt>Messages/s</dt><dd className="num">{n.alive ? n.events_per_sec : "–"}</dd></div>
                <div><dt>Requests/s</dt><dd className="num">{n.alive ? n.http_per_sec : "–"}</dd></div>
              </dl>
              {!n.alive && <div className="nc-note">No heartbeat for 3 seconds. Its devices reconnected to the other servers.</div>}
            </div>
          );
        })}
      </section>

      <div className="cl-grid">
        <section className="panel">
          <h2>Connections per server</h2>
          <p>NGINX sends each new WebSocket to the server with the fewest open connections (<code>least_conn</code>), so the lines rise together.</p>
          <div className="legend">
            {ids.map((id) => <span key={id} className="num"><Swatch k={idx(id, ids)} />{id}</span>)}
          </div>
          <Chart ids={ids} />
        </section>

        <section className="panel">
          <h2>Generate traffic</h2>
          <p>Each virtual listener is a real WebSocket opened from this browser. It goes through NGINX exactly like another phone connecting, but it can't enter anyone's private room.</p>
          <div className="btn-row">
            <button className="btn solid" onClick={() => fleet.add(10)}>Add 10 listeners</button>
            <button className="btn solid" onClick={() => fleet.add(50)}>Add 50 listeners</button>
            <button className="btn" onClick={() => fleet.rebalance()} disabled={!fleet.clients.length}>Rebalance</button>
            <button className="btn" onClick={() => fleet.removeAll()} disabled={!fleet.clients.length}>Remove all</button>
          </div>
          <label className="check">
            <input type="checkbox" checked={fleet.chatty} onChange={(e) => fleet.setChatty(e.target.checked)} />
            Busy mode: every listener sends a clock-sync message each second
          </label>
          <div className="split">
            {ids.map((id) => <span key={id} className="num">{id}: {fleetPer[id] || 0}</span>)}
          </div>

          <h3>Requests take turns</h3>
          <p className="muted" style={{ margin: "0 0 10px", fontSize: 13 }}>This page asks the cluster for its status every second. Short requests rotate across servers:</p>
          <div className="ribbon" aria-label="Which server answered each of the last requests">
            {recent.map((s, i) => {
              const n = s.server.replace(/\D/g, "") || "?";
              return <span key={s.t + i} className={`num n${((+n - 1) % 4) + 1}`}>{n}</span>;
            })}
          </div>
        </section>
      </div>

      <section className="panel">
        <h2>Fault tolerance demo</h2>
        <ol className="steps">
          <li>Add 50 listeners and start music in a room on a phone.</li>
          <li>In a terminal, stop a server: <code>docker compose stop flask2</code></li>
          <li>Within about 3 seconds its card shows down. Its devices reconnect to the other servers and the music keeps playing.</li>
          <li>Start it again with <code>docker compose start flask2</code>. New connections go to it first, since it has the fewest. Press Rebalance to spread everyone out again.</li>
        </ol>
      </section>
    </div>
  );
}
