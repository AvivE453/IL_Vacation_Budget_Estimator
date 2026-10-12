import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api/client";

// Retry what may pass next time (a busy 503, a 502 while the API restarts),
// not a 404 or 422 that will fail the same way again.
export function shouldRetry(failureCount: number, error: Error): boolean {
  const clientError = error instanceof ApiError && error.status < 500;
  return !clientError && failureCount < 3;
}

// One cache for the whole app: every component that asks for the same data
// shares one request and one copy of the answer.
export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });
}
