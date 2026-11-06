import { useState, useEffect } from "react";
import socket from "./socket";

const API = "/api";

export default function App() {
  const [rooms, setRooms] = useState([]);
  const [currentRoom, setCurrentRoom] = useState(null);
  const [playback, setPlayback] = useState({ is_playing: false, position_seconds: 0 });
  const [newRoomName, setNewRoomName] = useState("");
  const [connectedServer, setConnectedServer] = useState(null);

  // Load rooms on mount
  useEffect(() => {
    fetch(`${API}/rooms`)
      .then((r) => r.json())
      .then(setRooms);
  }, []);

  // Socket.IO lifecycle
  useEffect(() => {
    socket.on("joined", ({ room_id, server }) => {
      setConnectedServer(server);
    });

    socket.on("playback_update", (data) => {
      setPlayback((prev) => ({
        ...prev,
        is_playing: data.action === "play",
        position_seconds: data.position ?? prev.position_seconds,
      }));
    });

    return () => {
      socket.off("joined");
      socket.off("playback_update");
    };
  }, []);

  function joinRoom(room) {
    if (currentRoom) socket.emit("leave", { room_id: currentRoom.id });
    socket.emit("join", { room_id: room.id });
    setCurrentRoom(room);
    // Fetch current playback state
    fetch(`${API}/rooms/${room.id}`)
      .then((r) => r.json())
      .then((data) => data.playback && setPlayback(data.playback));
  }

  function sendCommand(action) {
    if (!currentRoom) return;
    socket.emit("playback_command", {
      room_id: currentRoom.id,
      action,
      position: playback.position_seconds,
    });
  }

  async function createRoom() {
    if (!newRoomName.trim()) return;
    const res = await fetch(`${API}/rooms`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newRoomName }),
    });
    const room = await res.json();
    setRooms((prev) => [...prev, room]);
    setNewRoomName("");
  }

  return (
    <div style={{ fontFamily: "sans-serif", maxWidth: 600, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>Multiroom Music Hub</h1>

      {connectedServer && (
        <p style={{ color: "#888", fontSize: 12 }}>Connected via: {connectedServer}</p>
      )}

      {/* Create room */}
      <section>
        <h2>Rooms</h2>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input
            value={newRoomName}
            onChange={(e) => setNewRoomName(e.target.value)}
            placeholder="New room name"
            style={{ flex: 1, padding: "6px 10px" }}
          />
          <button onClick={createRoom}>Create</button>
        </div>
        {rooms.map((room) => (
          <div
            key={room.id}
            onClick={() => joinRoom(room)}
            style={{
              padding: "10px 14px",
              marginBottom: 6,
              background: currentRoom?.id === room.id ? "#dbeafe" : "#f3f4f6",
              borderRadius: 6,
              cursor: "pointer",
              border: currentRoom?.id === room.id ? "2px solid #3b82f6" : "2px solid transparent",
            }}
          >
            {room.name}
          </div>
        ))}
      </section>

      {/* Playback controls */}
      {currentRoom && (
        <section style={{ marginTop: 24 }}>
          <h2>Now in: {currentRoom.name}</h2>
          <p>
            Status: <strong>{playback.is_playing ? "▶ Playing" : "⏸ Paused"}</strong>
            &nbsp;— position: {playback.position_seconds?.toFixed(1)}s
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={() => sendCommand("play")}
              disabled={playback.is_playing}
              style={{ padding: "8px 20px" }}
            >
              ▶ Play
            </button>
            <button
              onClick={() => sendCommand("pause")}
              disabled={!playback.is_playing}
              style={{ padding: "8px 20px" }}
            >
              ⏸ Pause
            </button>
          </div>
          <p style={{ fontSize: 12, color: "#888", marginTop: 8 }}>
            Commands are broadcast to all clients in this room, even those on the other Flask server.
          </p>
        </section>
      )}
    </div>
  );
}
