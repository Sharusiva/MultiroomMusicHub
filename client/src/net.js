import { io } from "socket.io-client";

// WebSocket-only transport: one long-lived TCP connection per client. Because no
// HTTP long-polling is involved, every request of a session hits the same node
// automatically, so NGINX can use least_conn instead of sticky ip_hash.
export function createSocket(auth) {
  return io("/", {
    path: "/socket.io",
    transports: ["websocket"],
    auth,
    forceNew: true,
    reconnectionDelay: 400,
    reconnectionDelayMax: 2000,
    timeout: 5000,
  });
}

// --- Login token ---------------------------------------------------------------
// Kept in localStorage so a phone stays logged in. The server stores only a hash of it.
let token = null;
try { token = localStorage.getItem("mmh-token"); } catch { /* storage blocked */ }
const authSubs = new Set();

export const getToken = () => token;
export function setToken(t) {
  token = t || null;
  try {
    if (token) localStorage.setItem("mmh-token", token);
    else localStorage.removeItem("mmh-token");
  } catch { /* ignore */ }
  authSubs.forEach((fn) => fn(token));
}
export function onAuthChange(fn) {
  authSubs.add(fn);
  return () => authSubs.delete(fn);
}

// --- REST helper that remembers which node served each request -------------
export const servedLog = [];
const servedSubs = new Set();

export function onServed(fn) {
  servedSubs.add(fn);
  return () => servedSubs.delete(fn);
}

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts = { ...opts, body: JSON.stringify(opts.json) };
  }
  const res = await fetch(`/api${path}`, { ...opts, headers });
  const server = res.headers.get("X-Served-By");
  if (server) {
    servedLog.push({ server, path, t: Date.now() });
    if (servedLog.length > 40) servedLog.shift();
    servedSubs.forEach((fn) => fn());
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && token && !path.startsWith("/auth/")) setToken(null); // session expired
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

// --- Virtual listeners: real Socket.IO clients opened from this browser -------
// Each one is a separate WebSocket that goes through NGINX, so the load balancer
// treats it exactly like another phone connecting. They can't join anyone's
// private room; they hold a connection and (in busy mode) send clock syncs.
class VirtualFleet {
  constructor() {
    this.clients = [];
    this.seq = 0;
    this.chatty = false;
    this.chatTimer = null;
    this.subs = new Set();
  }

  notify() {
    this.subs.forEach((fn) => fn());
  }

  subscribe(fn) {
    this.subs.add(fn);
    return () => this.subs.delete(fn);
  }

  add(n) {
    for (let i = 0; i < n; i++) {
      setTimeout(() => {
        const id = ++this.seq;
        const socket = createSocket({ kind: "virtual" });
        const c = { id, socket, server: null };
        socket.on("welcome", (w) => {
          c.server = w.server;
          this.notify();
        });
        socket.on("disconnect", () => {
          c.server = null;
          this.notify();
        });
        this.clients.push(c);
        this.notify();
      }, i * 20); // stagger like real devices arriving
    }
  }

  removeAll() {
    this.clients.forEach((c) => c.socket.disconnect());
    this.clients = [];
    this.notify();
  }

  // Disconnect + reconnect everyone so least_conn can spread them again
  // (e.g. after a crashed node comes back with zero connections).
  rebalance() {
    this.clients.forEach((c, i) => {
      c.socket.disconnect();
      c.server = null;
      setTimeout(() => c.socket.connect(), 100 + i * 15);
    });
    this.notify();
  }

  // Chatty mode: each listener sends a clock-sync message every second,
  // the same background traffic a real speaker produces, without changing playback.
  setChatty(on) {
    this.chatty = on;
    clearInterval(this.chatTimer);
    if (on) {
      this.chatTimer = setInterval(() => {
        this.clients.forEach((c) => c.socket.connected && c.socket.emit("time_sync", {}));
      }, 1000);
    }
    this.notify();
  }

  perServer() {
    const out = {};
    this.clients.forEach((c) => {
      if (c.server) out[c.server] = (out[c.server] || 0) + 1;
    });
    return out;
  }

  connectedCount() {
    return this.clients.filter((c) => c.server).length;
  }
}

export const fleet = new VirtualFleet();
