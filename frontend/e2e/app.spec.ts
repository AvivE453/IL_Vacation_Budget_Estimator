import { expect, type Page, test } from "@playwright/test";

// The data behind these numbers is tests/e2e_data.py: ILS at 0.25 USD,
// Barcelona $300 + 7 nights x $100, Rome $250 + 7 nights x $120.
const DEPART = "2030-06-01";
const RETURN = "2030-06-08";

async function fillSearch(page: Page, destination = "All destinations, cheapest first") {
  await page.goto("/");
  await page.getByLabel("Destination").selectOption({ label: destination });
  await page.getByLabel("Departure date").fill(DEPART);
  await page.getByLabel("Return date").fill(RETURN);
  await page.getByLabel("Budget", { exact: true }).fill("8000");
}

test("an estimate is ranked, saved, and found again in the history", async ({ page }) => {
  await fillSearch(page);
  await page.getByRole("button", { name: "Estimate" }).click();

  const rows = page.getByRole("table").getByRole("row");
  await expect(rows.nth(1)).toContainText("Barcelona");
  await expect(rows.nth(1)).toContainText("4000.00");
  await expect(rows.nth(2)).toContainText("Rome");
  await expect(rows.nth(2)).toContainText("4360.00");

  // Luxury: Barcelona 300 + 7 x 250 = $2050 = 8200 ILS, over the budget.
  await page.getByRole("button", { name: "luxury" }).click();
  await expect(page.getByText(/No destinations have both a flight and hotel price on file within your budget/)).toBeVisible();

  await page.getByRole("link", { name: "View this search's saved ranking" }).click();
  await expect(page).toHaveURL(/\/history\/\d+$/);
  await expect(page.getByRole("table").getByRole("row").nth(1)).toContainText("Barcelona");

  await page.getByRole("link", { name: "History" }).click();
  await expect(page.getByRole("table").getByRole("row").nth(1)).toContainText(`${DEPART}${RETURN}8000.00 ILS`);
});

test("a destination's view falls back to collected data and its date grid picks new dates", async ({ page }) => {
  await fillSearch(page, "Barcelona, Spain");
  await page.getByRole("button", { name: "Show this destination" }).click();

  await expect(page.getByRole("heading", { name: "Barcelona, Spain" })).toBeVisible();
  // Live search is off in these tests, so the view uses the collected price.
  await expect(page.getByText("No live answer just now - showing collected prices for these dates.")).toBeVisible();
  await expect(page.getByText(/1 of 1/)).toBeVisible();

  await expect(page.getByText(/Prices on file for 4 of 49 date pairs/)).toBeVisible();
  // The cheapest flight on file nearby: $210 = 840 ILS, out 3 days later and back a day early.
  await page.getByRole("button", { name: /Depart 2030-06-04, return 2030-06-07: flight 840.00 ILS/ }).click();

  await expect(page).toHaveURL(/depart_date=2030-06-04&return_date=2030-06-07/);
  await expect(page.getByText("From TLV, 2030-06-04 → 2030-06-07 (3 nights)", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hotels, 3 nights" })).toBeVisible();
});

test("the data-quality page shows the gaps", async ({ page }) => {
  await page.goto("/data-quality");

  const barcelona = page.getByRole("row", { name: /^Barcelona Spain/ });
  await expect(barcelona).toContainText("today");
  // Madrid has no data at all in these tests: a gap, not a zero price.
  await expect(page.getByRole("row", { name: /^Madrid Spain/ })).toContainText("0--");
});
