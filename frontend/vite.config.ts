import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the browser talks to Vite (5173) and Vite forwards API calls
// to the FastAPI backend (8000), so no CORS setup is needed (ADR 0004).
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": backend,
      "/chat": backend,
      "/feedback": backend,
    },
  },
});
