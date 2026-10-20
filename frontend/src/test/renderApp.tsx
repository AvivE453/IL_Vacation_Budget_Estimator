import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import App from "../App";
import { createQueryClient } from "../queryClient";

// The whole app at one URL, as a browser would show it: the real routes,
// pages and query client (a fresh, empty cache per test), with the URL kept
// in memory instead of the address bar.
export function renderApp(url: string) {
  const user = userEvent.setup();
  const client = createQueryClient();
  // The real retry rule without the waits between tries (1s, 2s, 4s), which
  // would make every test of a failing API take seven seconds.
  const defaults = client.getDefaultOptions();
  client.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retryDelay: 0 } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { user };
}
