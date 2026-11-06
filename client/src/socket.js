import { io } from "socket.io-client";

// In dev, Vite proxies /socket.io → NGINX → Flask (ip_hash picks a server)
const socket = io("/", { path: "/socket.io", transports: ["websocket", "polling"] });

export default socket;
