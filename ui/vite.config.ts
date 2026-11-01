import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The UI calls /api and /ws on its own origin; the dev server forwards them to the FastAPI
// backend (FLOWFORGE_API, default http://localhost:8000). No CORS, and no dependency on which
// port Vite ends up using.
// Read without @types/node (the UI tsconfig does not include Node types).
const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
const api = env?.FLOWFORGE_API ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: api, changeOrigin: true },
      "/ws": { target: api.replace(/^http/, "ws"), ws: true, changeOrigin: true },
    },
  },
});
