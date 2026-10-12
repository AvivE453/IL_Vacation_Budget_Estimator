import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development the browser asks Vite (port 5173) for /api/..., and Vite
    // passes it on to FastAPI (port 8000). To the browser it's all one origin,
    // so no CORS setup and the session cookie just works. API_URL points it at
    // another API instead - the end-to-end tests' (playwright.config.ts).
    proxy: {
      "/api": process.env.API_URL ?? "http://127.0.0.1:8000",
    },
  },
  test: {
    // A simulated browser (document, window) for rendering components in Node.
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // e2e/ holds the Playwright tests, which run against the real app instead.
    include: ["src/**/*.test.{ts,tsx}"],
    // The users' time zone, on every machine (CI runs in UTC): date code has
    // to be right where the local and UTC dates differ.
    env: { TZ: "Asia/Jerusalem" },
  },
});
