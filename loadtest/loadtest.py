"""
Load test for Multiroom Music Hub.

Signs up a throwaway account, creates a private test room, opens N real
Socket.IO clients through NGINX logged in as that account, joins them all to the
room, then measures:
  * connection time and how NGINX spread clients across nodes
  * fan-out latency: time from one client sending a command until every
    listener in the room has received the new state (across all nodes)
  * clock-sync round-trip time

Usage (stack must be running):
    pip install "python-socketio[asyncio_client]" aiohttp
    python loadtest/loadtest.py --url http://localhost --clients 200
or with Docker:
    docker compose --profile loadtest run --rm loadtest --clients 200
"""
import argparse
import asyncio
import json
import random
import statistics
import time

import aiohttp
import socketio


def pct(values, p):
    if not values:
        return float("nan")
    values = sorted(values)
    k = min(len(values) - 1, max(0, round(p / 100 * (len(values) - 1))))
    return values[k]


def summary(name, values, unit="ms"):
    if not values:
        return f"{name:<28} (no samples)"
    return (f"{name:<28} n={len(values):<5} p50={pct(values, 50):7.1f}{unit}  "
            f"p95={pct(values, 95):7.1f}{unit}  max={max(values):7.1f}{unit}")


class Listener:
    def __init__(self, idx, url, room_id, results, token):
        self.idx = idx
        self.token = token
        self.url = url
        self.room_id = room_id
        self.results = results
        self.server = None
        self.sio = socketio.AsyncClient(reconnection=True, reconnection_delay=0.5)
        self.sio.on("state", self.on_state)

    async def on_state(self, data):
        # record arrival time; matched with the send time after the run
        self.results["arrivals"].setdefault(data.get("version"), []).append(time.perf_counter())

    async def start(self):
        t0 = time.perf_counter()
        await self.sio.connect(self.url, transports=["websocket"], socketio_path="socket.io",
                               auth={"token": self.token, "device": f"loadtest-{self.idx}"}, wait_timeout=10)
        resp = await self.sio.call("join", {"room_id": self.room_id}, timeout=10)
        self.results["connect"].append((time.perf_counter() - t0) * 1000)
        self.server = resp.get("server")

    async def time_sync(self):
        t0 = time.perf_counter()
        await self.sio.call("time_sync", {}, timeout=5)
        self.results["rtt"].append((time.perf_counter() - t0) * 1000)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost")
    ap.add_argument("--clients", type=int, default=100)
    ap.add_argument("--rate", type=float, default=50, help="new connections per second")
    ap.add_argument("--commands", type=int, default=20, help="number of broadcast commands to time")
    ap.add_argument("--out", default="loadtest-results.json")
    args = ap.parse_args()

    async with aiohttp.ClientSession() as http:
        creds = {"username": f"loadtest-{random.randrange(10**8)}", "password": f"lt-{random.randrange(10**12)}"}
        async with http.post(f"{args.url}/api/auth/signup", json=creds) as r:
            account = await r.json()
            if r.status != 201:
                raise SystemExit(f"Could not create the load-test account: {account.get('error')}")
        token = account["token"]
        headers = {"Authorization": f"Bearer {token}"}
        async with http.post(f"{args.url}/api/rooms", headers=headers,
                             json={"name": f"Load test {time.strftime('%H:%M:%S')}"}) as r:
            room = await r.json()
        async with http.get(f"{args.url}/api/tracks", headers=headers) as r:
            tracks = await r.json()

    results = {"connect": [], "fanout": [], "rtt": [], "pending": {}, "arrivals": {}}
    listeners = [Listener(i, args.url, room["id"], results, token) for i in range(args.clients)]
    print(f"Connecting {args.clients} clients at {args.rate:.0f}/s to {args.url} ...")
    t_start = time.perf_counter()
    tasks = []
    for lst in listeners:
        tasks.append(asyncio.create_task(lst.start()))
        await asyncio.sleep(1 / args.rate)
    done = await asyncio.gather(*tasks, return_exceptions=True)
    failed = sum(1 for d in done if isinstance(d, Exception))
    connected = [lst for lst in listeners if lst.server]
    print(f"  connected {len(connected)}/{args.clients} in {time.perf_counter() - t_start:.1f}s ({failed} failed)")

    dist = {}
    for lst in connected:
        dist[lst.server] = dist.get(lst.server, 0) + 1
    print("\nLoad balancer distribution (least_conn):")
    for server, n in sorted(dist.items()):
        print(f"  {server:<10} {n:>5}  {'#' * max(1, round(40 * n / max(dist.values())))}")

    # Fan-out latency: one random client changes the playback, measure until all receive it.
    controller = connected[0]
    if tracks:
        await controller.sio.call("command", {"room_id": room["id"], "action": "queue_add",
                                              "track_id": tracks[0]["id"]}, timeout=10)
    await asyncio.sleep(1)
    for i in range(args.commands):
        sender = random.choice(connected)
        t = time.perf_counter()
        resp = await sender.sio.call("command", {"room_id": room["id"], "action": "seek",
                                                 "position": random.uniform(0, 60)}, timeout=10)
        if resp and resp.get("version") is not None:
            results["pending"][resp["version"]] = t
        await asyncio.sleep(0.4)
    await asyncio.sleep(1)
    for version, sent in results["pending"].items():
        for arrived in results["arrivals"].get(version, []):
            results["fanout"].append((arrived - sent) * 1000)

    # Clock sync RTT under load
    await asyncio.gather(*[lst.time_sync() for lst in random.sample(connected, min(100, len(connected)))])

    print("\nResults:")
    print(" ", summary("Connect + join", results["connect"]))
    print(" ", summary("Command fan-out to all", results["fanout"]))
    print(" ", summary("Clock-sync round trip", results["rtt"]))
    expected = len(results["pending"]) * len(connected)
    print(f"  Fan-out deliveries: {len(results['fanout'])}/{expected} (every listener got every update)"
          if len(results["fanout"]) == expected else
          f"  Fan-out deliveries: {len(results['fanout'])}/{expected} (some updates were not received)")

    with open(args.out, "w") as f:
        json.dump({
            "clients": args.clients, "connected": len(connected), "distribution": dist,
            "connect_ms": {"p50": pct(results["connect"], 50), "p95": pct(results["connect"], 95)},
            "fanout_ms": {"p50": pct(results["fanout"], 50), "p95": pct(results["fanout"], 95),
                          "max": max(results["fanout"]) if results["fanout"] else None},
            "rtt_ms": {"p50": pct(results["rtt"], 50), "p95": pct(results["rtt"], 95)},
        }, f, indent=2)
    print(f"\nSaved {args.out}")
    await asyncio.gather(*[lst.sio.disconnect() for lst in listeners], return_exceptions=True)
    async with aiohttp.ClientSession() as http:
        await http.delete(f"{args.url}/api/rooms/{room['id']}")


if __name__ == "__main__":
    asyncio.run(main())
