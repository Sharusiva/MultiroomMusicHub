// Clock synchronization with the server (Cristian's algorithm).
//
// Each device's clock is off from the server's by some unknown amount. We ask the
// server for its time and measure the round trip:
//
//     t0 = local send time,  ts = server time,  t1 = local receive time
//     offset ≈ ts - (t0 + t1) / 2
//
// The sample with the smallest round-trip time is the most trustworthy (least
// queueing delay), so we keep a sliding window and use the best one.

const wall = () => performance.timeOrigin + performance.now();

export class ClockSync {
  constructor() {
    this.socket = null;
    this.samples = [];
    this.offset = 0; // ms to add to the local clock to get server time
    this.rtt = null; // ms
    this.synced = false;
    this.listeners = new Set();
    this.timer = null;
  }

  attach(socket) {
    this.socket = socket;
    this.samples = [];
    clearInterval(this.timer);
    const onConnect = () => {
      this.samples = []; // new server might have a different clock; start fresh
      this.burst(8);
    };
    socket.on("connect", onConnect);
    if (socket.connected) onConnect();
    this.timer = setInterval(() => this.burst(2), 5000);
  }

  sampleOnce() {
    return new Promise((resolve) => {
      if (!this.socket?.connected) return resolve(null);
      const t0 = wall();
      this.socket.timeout(2000).emit("time_sync", {}, (err, resp) => {
        if (err || !resp) return resolve(null);
        const t1 = wall();
        resolve({ rtt: t1 - t0, offset: resp.server_ms - (t0 + t1) / 2 });
      });
    });
  }

  async burst(n) {
    for (let i = 0; i < n; i++) {
      const s = await this.sampleOnce();
      if (s) this.samples.push(s);
      if (this.samples.length > 16) this.samples.shift();
    }
    if (!this.samples.length) return;
    const best = this.samples.reduce((a, b) => (b.rtt < a.rtt ? b : a));
    this.offset = best.offset;
    this.rtt = best.rtt;
    this.synced = true;
    this.listeners.forEach((fn) => fn(this));
  }

  now() {
    return wall() + this.offset;
  }

  onChange(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
}
