import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Production: `docker compose up` builds this app and NGINX serves it on port 80.
// Development: run the stack with Docker, then `npm run dev` here for hot reload;
// API, WebSocket and audio requests are proxied to NGINX on localhost:80.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": "http://localhost:80",
      "/media": "http://localhost:80",
      "/socket.io": { target: "http://localhost:80", ws: true },
    },
  },
});
