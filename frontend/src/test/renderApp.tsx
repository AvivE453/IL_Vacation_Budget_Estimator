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
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[url]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { user };
}
