import { defineConfig, devices } from "@playwright/test";

// End-to-end: a real browser against the real app - Vite, FastAPI and
// Postgres - with fixed data (tests/e2e_data.py) and no live flight search.
// Ports 5174/8001, not the dev servers' 5173/8000, so both can run at once.
const API_PORT = 8001;
const WEB_PORT = 5174;

export default defineConfig({
  testDir: "e2e",
  // Each test writes searches to the same database and session - one at a time.
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    ...devices["Desktop Chrome"],
    // Google Chrome itself rather than Playwright's own Chromium build, which
    // Playwright no longer ships for Ubuntu 20.04 (the dev machine). CI
    // installs Chrome with `npx playwright install chrome`.
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // Rebuilds vacation_budget_e2e, then serves the API on it.
      command: `uv run python -m tests.e2e_server ${API_PORT}`,
      cwd: "..",
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      env: { API_URL: `http://127.0.0.1:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
    },
  ],
});
