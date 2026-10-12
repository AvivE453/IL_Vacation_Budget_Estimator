import { within } from "@testing-library/react";

// The text of each cell in a table row, e.g. ["Madrid", "Spain", "0", "-", "-"].
// Pieces of text inside a cell are joined by a space, as a reader sees them -
// textContent would run "1400.00<br>Air France" together.
export function cellTexts(row: HTMLElement): string[] {
  return within(row)
    .getAllByRole("cell")
    .map((cell) => {
      const pieces: string[] = [];
      const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        pieces.push(walker.currentNode.textContent ?? "");
      }
      return pieces.join(" ").replace(/\s+/g, " ").trim();
    });
}

// The body rows of a table, without its header row.
export function bodyRows(table: HTMLElement): HTMLElement[] {
  return within(table).getAllByRole("row").slice(1);
}
