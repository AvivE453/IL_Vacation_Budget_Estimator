import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development the browser asks Vite (port 5173) for /api/..., and Vite
    // passes it on to FastAPI (port 8000). To the browser it's all one origin,
    // so no CORS setup and the session cookie just works.
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
