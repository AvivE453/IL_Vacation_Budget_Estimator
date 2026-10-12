import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { ApiError } from "./api/client";
import App from "./App";
import "./styles.css";

// One cache for the whole app: every component that asks for the same data
// shares one request and one copy of the answer.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry what may pass next time (a busy 503, a 502 while the API
      // restarts), not a 404 or 422 that will fail the same way again.
      retry: (failureCount, error) => {
        const clientError = error instanceof ApiError && error.status < 500;
        return !clientError && failureCount < 3;
      },
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
