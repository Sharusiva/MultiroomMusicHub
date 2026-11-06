# Multiroom Music Hub

## Quick start

```bash
docker compose up --build
```

Then open http://localhost:5173 in two separate browser tabs (or two browsers).

- Tab A will connect to one Flask server, Tab B to the other (NGINX ip_hash)
- Create a room → both tabs join it
- Press Play/Pause in Tab A → Tab B reflects the change instantly (via Redis pub/sub)

## Architecture

```
React Clients
     │
  NGINX :80  (round-robin REST, ip_hash WebSocket)
  ┌────┴────┐
Flask1    Flask2   (REST + Socket.IO)
  └────┬────┘
     Redis   (pub/sub channel: room_events)
     │
 PostgreSQL  (rooms, tracks, playback_state)
```

## REST endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Server identity |
| GET | /api/rooms | List all rooms |
| POST | /api/rooms | Create room `{"name":"..."}` |
| GET | /api/rooms/:id | Room + playback state |
| POST | /api/rooms/:id/tracks | Add track |

## Socket.IO events

| Direction | Event | Payload |
|-----------|-------|---------|
| Client → Server | `join` | `{room_id}` |
| Client → Server | `leave` | `{room_id}` |
| Client → Server | `playback_command` | `{room_id, action, position}` |
| Server → Client | `joined` | `{room_id, server}` |
| Server → Client | `playback_update` | `{room_id, action, position}` |

## Cross-server event flow (the key mechanism)

1. Client A (on Flask 1) emits `playback_command {action: "pause"}`
2. Flask 1 persists to PostgreSQL and emits locally to its room subscribers
3. Flask 1 publishes the event to the Redis `room_events` channel
4. Flask 2's subscriber thread receives the event, filters out its own (by `origin_server`)
5. Flask 2 emits `playback_update` to its locally-connected clients in that room
6. Client B (on Flask 2) sees the pause
