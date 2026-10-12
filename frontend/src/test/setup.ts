// Runs before every test file (vite.config.ts -> test.setupFiles).
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach } from "vitest";

import { server } from "./server";

// Listening now, not in beforeAll: this file runs before each test file's
// imports, and openapi-fetch keeps the fetch it finds when the client is
// created - it has to find MSW's. A request no test answered fails the test
// instead of quietly reaching the network.
server.listen({ onUnhandledFrame: "error" });
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
