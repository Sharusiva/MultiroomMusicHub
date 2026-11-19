# Multiroom Music Hub

A distributed music player with private listening rooms. Sign up, create a room,
and invite friends with its 6-character code. Every phone, laptop and tablet in
the room plays the same song in sync, while other rooms play their own music.

Behind the scenes, three identical Flask servers sit behind an NGINX load
balancer and share state through PostgreSQL and Redis, so any server can fail
without the music stopping.

## Contents

1. [Requirements](#1-requirements)
2. [Run the app](#2-run-the-app)
3. [Use the app](#3-use-the-app)
4. [Stop, restart and reset](#4-stop-restart-and-reset)
5. [Troubleshooting](#5-troubleshooting)
6. [Demo script](#6-demo-script)
7. [Load test](#7-load-test)
8. [How it works](#8-how-it-works)
9. [Security](#9-security)
10. [Project layout and development](#10-project-layout-and-development)
11. [API reference](#11-api-reference)

---

## 1. Requirements

| You need | Why |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Runs everything: NGINX, 3 Flask servers, PostgreSQL and Redis. You don't need Node or Python installed |
| A terminal | Terminal on macOS, PowerShell on Windows |
| One Wi-Fi network for all devices | Phones and laptops reach the hub through the host computer's local IP address |

The first build downloads images and packages, so the first start takes a few
minutes and needs internet. After that it starts in seconds.

---

## 2. Run the app

### Step 1: Start Docker Desktop

Open Docker Desktop and wait until it says it's running.

### Step 2: Get the code

```bash
git clone https://github.com/Sharusiva/Multiroom-Music-Hub.git
cd Multiroom-Music-Hub
```

(If you already have the folder, just `cd` into it.)

### Step 3: Start the hub

**macOS or Linux:**

```bash
./start.sh
```

**Windows (PowerShell):** find your Wi-Fi IP with `ipconfig` (the "IPv4 Address"
line, e.g. `192.168.1.42`), then:

```powershell
$env:PUBLIC_HOST="192.168.1.42"
docker compose up --build
```

`start.sh` does the same thing automatically: it finds your Wi-Fi IP, prints the
addresses to use, and runs `docker compose up --build`. The IP is only used for
invite links and QR codes; everything else works without it.

### Step 4: Wait until it's ready

The terminal shows logs from every service. It's ready when you see a line like
this from each of the three servers:

```
flask1-1  | [flask1] listening on :5000
flask2-1  | [flask2] listening on :5000
flask3-1  | [flask3] listening on :5000
```

Leave this terminal open; closing it or pressing `Ctrl+C` stops the hub.

### Step 5: Open it

| Where | Address |
|---|---|
| On the computer running the hub | http://localhost |
| On phones and other laptops (same Wi-Fi) | http://YOUR-IP, e.g. http://192.168.1.42 (printed by `start.sh`), or scan a room's invite QR code |
| Cluster dashboard, for demos | http://localhost/cluster (nothing in the app links to it; type the address) |

Port 80 already in use? Run `HTTP_PORT=8080 ./start.sh` and add `:8080` to every
address above.

---

## 3. Use the app

The app starts empty: no accounts, no rooms.

1. **Sign up.** Pick a username and a password of at least 8 characters.
2. **Create a room.** On the home screen, give it a name and press **Create**.
   The room opens and shows its invite: a code like `274 CC3`, a QR code and a link.
3. **Invite people.** They open the link or scan the QR code, sign up or log in,
   and land in the room. Or they open the hub's address and type the code under
   **Join with a code**. Nobody can see a room without its code.
4. **Add music.** Open **Library**, press **+** on songs (10 come built in), or
   **Upload** your own. They appear in **Up next**.
5. **Play.** Press play on any device. Every device in the room plays in sync,
   and any device can pause, skip, seek or reorder.
6. **More rooms and zones.** Make another room for different music. To play the
   same song in two of your rooms, open the rooms drawer (speaker button, bottom
   right) and press **Link**. **Split zone** separates them again.

| Where | What you can do there |
|---|---|
| Top bar | Room name and code (tap to copy), **Invite**, account menu (your rooms, reset code, leave room, log out) |
| Pill under the song title | Format, sample rate and sync drift; tap it to see the full signal path |
| Bottom bar | Play controls, seek bar, rooms drawer, this room's volume |
| Rooms drawer | Switch rooms, link rooms into a zone, room and zone volume, create or join rooms |

Room owners can **reset the invite code** (the old code stops working) or delete
the room. Members can leave it.

---

## 4. Stop, restart and reset

| To | Run |
|---|---|
| Stop | `Ctrl+C` in the terminal running the hub, or `docker compose down` |
| Start again | `./start.sh` (or `docker compose up --build`) |
| Apply code changes | `./start.sh` again; it rebuilds automatically |
| Wipe all accounts, rooms and queues | `docker compose down -v`, then start again |
| Clean up containers from older versions | `docker compose down -v --remove-orphans` |
| Simulate a server crash | `docker compose stop flask2`; bring it back with `docker compose start flask2` |

Logins are kept in Redis, which is cleared by `docker compose down`, so you'll be
asked to log in again after a restart. Accounts and rooms stay in PostgreSQL
unless you use `-v`.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| Phones can't open the page | They must be on the same Wi-Fi as the computer. University and public networks often block devices from reaching each other ("client isolation"). Turn on a **phone hotspot** and connect the computer and phones to it. On macOS, allow incoming connections for Docker if the firewall asks |
| Invite has no QR code, only the code | The hub doesn't know your IP. Start it with `./start.sh` (or set `PUBLIC_HOST` on Windows). The code still works |
| No sound on a phone | Browsers only allow audio after a tap. Tap play once, and check the phone isn't muted |
| You still see an old version | NGINX serves the app built into its Docker image, so rebuild with `./start.sh`. If it persists, run `docker compose down --remove-orphans` first (older versions ran a separate app on port 5173), and use http://localhost, not `:5173` |
| `permission denied: ./start.sh` | Run `chmod +x start.sh` once |
| Port 80 in use | `HTTP_PORT=8080 ./start.sh`, then use http://YOUR-IP:8080 |
| Logged out unexpectedly | Logins are kept in Redis, which `docker compose down` clears. Log in again |
| Errors about database columns or tables after updating | Reset once with `docker compose down -v` |

---

## 6. Demo script

About 5 minutes, with a laptop and two phones.

1. **Start:** run `./start.sh`. On the laptop open http://localhost and sign up.
   Open http://localhost/cluster in a second tab for later.
2. **Private rooms:** create a room (say *Friday Night*); the invite shows its
   code and QR code. On phone A, sign up as someone else: the home screen is
   empty, because nothing is visible without a code. Scan the QR code and phone A
   lands in the room.
3. **Sync:** add songs from Library and press play. Hold the laptop and phone
   together: no echo. Pause or skip on either; both follow. Tap the pill under
   the song title to show the signal path and live drift.
4. **Multiple rooms and zones:** create a second room and move phone B into it;
   it plays its own music. In the rooms drawer, press **Link** on it: its card
   slides into your zone and phone B switches to your song at the same position.
   Drag the zone volume and both rooms follow.
   Then, without leaving your room, open **Library**, press the cast button on a
   song and choose **Play** next to the other room: phone B starts that song.
   The speaker list under the song shows each device's live status and drift.
5. **Load balancer:** switch to the `/cluster` tab. Press **Add 50 listeners**
   and watch the connections split evenly across the three servers; turn on
   **Busy mode** for steady traffic. The round-robin strip shows REST requests
   rotating 1 → 2 → 3.
6. **Fault tolerance:** run `docker compose stop flask2`. Within about 3 seconds
   its card shows *down*, its connections move to flask1 and flask3, and the music
   keeps playing. Run `docker compose start flask2`, then press **Rebalance**.
7. **Security:** on a phone, open `http://YOUR-IP/api/rooms` without logging in
   (it returns 401), or enter a wrong code several times (it gets blocked).
8. **Numbers:** run the load test (next section).

---

## 7. Load test

With the hub running, in a second terminal:

```bash
docker compose --profile loadtest run --rm loadtest --clients 300
```

It signs up a throwaway account, creates a private test room, connects 300
logged-in WebSocket clients through NGINX, and measures how they spread across
servers and how fast updates reach everyone. Results are also saved to
`loadtest/loadtest-results.json`.

Results with 300 clients and 3 servers:

| Metric | p50 | p95 | max |
|---|---|---|---|
| Connect + authenticate + join room | 63.1 ms | 185.3 ms | 308 ms |
| Command fan-out to every listener (across all servers) | 23.4 ms | 34.7 ms | 40.2 ms |
| Clock-sync round trip | 21.2 ms | 28.1 ms | 29.0 ms |

- Distribution: flask1 100 / flask2 100 / flask3 100
- Delivery: 6000 / 6000 updates received (no lost messages)
- Playback offset between two devices on different servers: about 10–30 ms
- Checking the login and room membership on every connection made connecting
  slower than before accounts existed (p95 was 65 ms), with no effect on
  playback updates

---

## 8. How it works

### Architecture

```
  Phones / laptops / tablets  (React app, one WebSocket each)
                 │
        NGINX :80 ─ serves the React app and /media audio files
          │   /api/*        → round robin      (short, stateless)
          │   /socket.io/*  → least_conn       (long-lived WebSockets)
   ┌──────┼──────┐
 flask1 flask2 flask3   identical Flask + Socket.IO servers, no shared memory
   └──────┼──────┘
     ┌────┴─────┐
   Redis       PostgreSQL
   pub/sub     users, rooms, members,
   live state  queues, tracks,
   sessions    playback state (row-locked)
   presence
   device status
   heartbeats
   rate limits
```

### Features

| Feature | How |
|---|---|
| Open from any device on the network | NGINX serves the app, API, WebSockets and audio on one port (80) on all network interfaces |
| Accounts | Passwords stored as salted scrypt hashes; logins shared by all servers through Redis |
| Private rooms with invite codes | You only see rooms you created or joined. Others join with the code or invite link (`/?join=CODE`) |
| Different music in different rooms | Each room has its own queue and playback state in PostgreSQL |
| Edit and delete uploads | Uploads get a readable title and artist from their file tags or filename (`Artist - Title.mp3`, or Pixabay's `artist-song-title-123456.mp3`). The ⋯ menu on a song you uploaded lets you fix the title and artist, or delete it, which removes it from the library and every room's queue (two taps to confirm). Uploads whose file has gone missing are cleaned up at startup |
| Send music to another room | In Library, the cast button on a song sends it to any of your other rooms (**Queue** or **Play**) without leaving the room you're in |
| Speaker status | Every device reports what it's really doing every 2 s (playing, paused, buffering, needs a tap) and its drift. Each speaker shows *in sync*, *catching up*, *out of sync* or *not responding* |
| Live state in Redis | Each room's current playback state is cached in Redis after every command, so joins and room lists don't hit PostgreSQL |
| Synchronized playback | Clock sync (Cristian's algorithm) + scheduled start + drift correction |
| Zones | Linked rooms play the same song in sync |
| Synced volume | Each room has one volume shared by its devices; a zone's master fader scales linked rooms proportionally |
| Signal path | The pill under the song opens the chain: file, NGINX, server, clock sync, scheduler, output, zone |
| Music library | 10 original, royalty-free tracks with original covers, plus uploads. Uploads (MP3, M4A, WAV, FLAC…) are re-encoded with ffmpeg to the same CBR 192 kbps / 44.1 kHz MP3 as the built-in songs, so every browser (Safari included) seeks and syncs them accurately |
| Cluster dashboard | At `/cluster` only: connections per server, messages/s, round-robin strip, virtual listener generator |
| Fault tolerance | Stop any Flask server; its devices reconnect to the others and keep playing |

### Distributed systems concepts

- **Load balancing:** REST requests are round-robined; WebSockets go to the
  server with the fewest open connections (`least_conn`). Clients use
  WebSocket-only transport, so no sticky sessions (`ip_hash`) are needed, and
  many devices behind one IP still spread out.
- **Message passing / pub-sub:** Flask-SocketIO uses Redis as a message queue. A
  command handled on flask1 is published to Redis and delivered by every server
  to its own sockets in that room.
- **Clock synchronization:** each device estimates its offset from server time
  with Cristian's algorithm (`client/src/clock.js`), keeping the sample with the
  lowest round-trip time.
- **Synchronized playback without streaming positions:** the server stores an
  anchor, "at server time `anchor_ms` the song is at `offset` seconds". Every
  play, seek and skip is scheduled 600 ms in the future so all devices receive it
  before they start. Each device computes its target position from its synced
  clock and corrects drift every 250 ms (tiny `playbackRate` nudges, or a seek if
  it is more than 200 ms off). See `client/src/syncPlayer.js`.
- **Zones (group membership):** a linked room stores a `group_leader`. Its
  devices subscribe to the leader's playback channel (`play:<leader>`), and any
  command they send is applied to the leader's state, so every room in the zone
  hears exactly the same anchor. Linking or splitting broadcasts `regroup`, and
  affected devices re-join their new zone without reloading.
- **Concurrency control:** commands lock the room's playback row
  (`SELECT … FOR UPDATE`), so simultaneous button presses on different servers
  are serialized. A `version` number keeps updates ordered and makes
  `track_ended` idempotent (only the first device to report the end of a song
  advances it).
- **Distributed mutual exclusion:** a PostgreSQL advisory lock ensures only one
  server creates tables and runs migrations when all three start at once.
- **Failure detection:** each server writes a heartbeat to Redis every second
  with a 3-second expiry. If it expires, the server is marked down and its
  clients are cleaned up; their browsers reconnect through NGINX to a healthy
  server and re-join their room.
- **Shared session store:** a login issued by flask1 is checked by flask2 or
  flask3 against Redis, so any server can handle any request. Logging out deletes
  the session for every server at once.
- **Room-node status reports:** devices send `status` every 2 s (and at once
  when it changes). The controller derives a health value, keeps the report in
  Redis (`status:<sid>`, 8-second expiry) and re-broadcasts the speaker list only
  when a device's health changes, so steady devices cost no extra messages. A
  device whose reports stop is shown as *not responding* even though its socket
  is still open.
- **Live state cache:** PostgreSQL is still the only place commands are applied
  (under the row lock). After each commit the new state is written to Redis
  (`live:<room_id>`) with a compare-and-set on `version`, so a slower node can
  never overwrite newer state with older. A cache miss reads PostgreSQL and
  refills Redis. Hits and misses per server appear in `/api/cluster`.
- **Transparency:** users never see which server they're on unless they look
  (the signal path and speaker list show it for the demo).

---

## 9. Security

| Threat | Protection |
|---|---|
| Browsing rooms you weren't invited to | There is no "list all rooms" endpoint. `/api/rooms` returns only rooms you belong to, and every room endpoint and socket event checks membership. A room that isn't yours returns the same 404 as one that doesn't exist, so room ids can't be probed |
| Guessing room codes | 6 characters from a 31-symbol alphabet (about 887 million codes); 15 wrong codes per account blocks joining for 10 minutes |
| A leaked code | The owner can reset it; the old code stops working immediately and members stay |
| A stolen database | Passwords are salted scrypt hashes (Werkzeug); Redis stores only SHA-256 hashes of login tokens, so a dump can't be replayed as logins |
| Password guessing | 10 wrong passwords per username and IP blocks login for 10 minutes. Login always runs one hash check, so response time doesn't reveal which usernames exist |
| Controlling a room you left | Commands are accepted only for the room your socket joined, and only while you're still a member. Leaving or deletion disconnects your open sockets from the room |
| Unauthenticated sockets | The WebSocket handshake requires a valid login token (`connect_error: unauthorized` otherwise). Only the dashboard's virtual listeners connect without one, and they can't join rooms |
| Malicious uploads | Logged-in users only, 50 MB limit, 60 per hour, audio file types only, files saved under random names, and files that don't parse as audio are rejected |
| Spam accounts and rooms | Up to 20 owned rooms per account; 30 sign-ups per hour per network |

Known limits (fine for a local-network demo): traffic is plain HTTP (put NGINX
behind TLS for anything public), audio files in `/media` are readable by anyone
on the network who knows a file name, and the `/cluster` dashboard is unlisted
rather than password protected.

---

## 10. Project layout and development

```
client/      React app (Vite): login, rooms, stage, queue, rooms drawer,
             cluster dashboard, sync engine (Radix UI, Motion, Lucide icons)
server/      Flask + Socket.IO server (app.py: accounts, rooms, sync), models,
             library scanner
nginx/       NGINX config + Dockerfile (builds the client and serves it)
media/       Audio files, covers/, library.json (uploads go to media/uploads/)
loadtest/    Load-testing tool
tools/       Music and cover generators
start.sh     Finds your Wi-Fi IP and starts everything
```

**Live UI editing** (needs Node 20+): keep the hub running, then in a second
terminal:

```bash
cd client
npm install
npm run dev     # http://localhost:5173, changes appear instantly
```

**Regenerate the built-in music and covers** (needs Python with numpy and
scipy, plus ffmpeg):

```bash
python tools/generate_music.py              # all tracks
python tools/generate_music.py mirrorball   # just one
python tools/generate_covers.py
```

---

## 11. API reference

### REST

Endpoints marked 🔒 need `Authorization: Bearer <token>` from signup or login.

| Method | Path | Description |
|---|---|---|
| GET | /api/health | Server identity |
| GET | /api/info | Public URL for invite links |
| GET | /api/time | Server time |
| POST | /api/auth/signup | `{"username", "password"}` → `{token, user}` |
| POST | /api/auth/login | `{"username", "password"}` → `{token, user}` |
| POST | /api/auth/logout | Ends the session on every server |
| GET | /api/auth/me 🔒 | The logged-in user |
| GET | /api/tracks 🔒 | Music library |
| POST | /api/tracks 🔒 | Upload a song (multipart `file`) |
| PATCH | /api/tracks/:id 🔒 | Rename a song you uploaded `{"title", "artist"}`; devices update live |
| DELETE | /api/tracks/:id 🔒 | Delete a song you uploaded (built-ins can't be deleted); it's removed from every queue |
| GET | /api/rooms 🔒 | Your rooms only, with codes, devices and now playing |
| POST | /api/rooms 🔒 | Create a room `{"name"}`; you become its owner |
| POST | /api/rooms/join 🔒 | Join with `{"code"}` |
| GET | /api/rooms/:id 🔒 | Playback state + queue (members only) |
| POST | /api/rooms/:id/code 🔒 | Owner: issue a new invite code |
| POST | /api/rooms/:id/leave 🔒 | Member: leave the room |
| DELETE | /api/rooms/:id 🔒 | Owner: delete the room for everyone |
| POST | /api/rooms/:id/link 🔒 | Link into another of your rooms' zone `{"to": "<room id>"}` |
| POST | /api/rooms/:id/unlink 🔒 | Take a room out of its zone (on the leader: split the zone) |
| POST | /api/rooms/:id/queue 🔒 | Send a song to any of your rooms `{"track_id", "play": false}` (`play: true` starts it there) |
| GET | /api/rooms/:id/devices 🔒 | Every device in the zone with its latest status report and health |
| GET | /api/cluster | Server heartbeats and connection counts (no user or room data) |

### Socket.IO events

The handshake must carry `auth: {token, device}`; it's refused otherwise.

| Direction | Event | Payload |
|---|---|---|
| Client → Server | `join` | `{room_id}` (members only) → state, queue, presence |
| Client → Server | `leave` | `{}` |
| Client → Server | `command` | `{room_id, action, ...}` with action `play`, `pause`, `seek`, `next`, `prev`, `jump`, `track_ended`, `queue_add`, `queue_remove`, `queue_clear` |
| Client → Server | `time_sync` | `{}` → `{server_ms}` |
| Client → Server | `status` | `{room_id, state, position, drift_ms, version, track_id}` every 2 s |
| Client → Server | `set_volumes` | `{volumes: {room_id: 0-100}}` (your rooms only) |
| Server → Client | `state` | Playback anchor, track, version |
| Server → Client | `queue` | Room queue |
| Server → Client | `presence` | Devices in the zone, their servers, and each one's status and health |
| Server → Client | `volumes` | Room volumes that changed (sent only to members) |
| Server → Client | `regroup` | Rooms whose zone changed (re-join) |
| Server → Client | `room_closed` | The room was deleted, or you left it |
| Server → Client | `library_changed`, `rooms_changed` | Refresh hints (`rooms_changed` only to members) |
