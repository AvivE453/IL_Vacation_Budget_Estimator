import { expect, type Page, test } from "@playwright/test";

// The data behind these numbers is tests/e2e_data.py: ILS at 0.25 USD,
// Barcelona $300 a seat + $100 a room-night, Rome $250 + $120. The form's
// default party is a couple in one room: 2 seats + 7 nights.
const DEPART = "2030-06-01";
const RETURN = "2030-06-08";

async function fillDatesAndBudget(page: Page) {
  await page.goto("/");
  await page.getByLabel("תאריך יציאה").fill(DEPART);
  await page.getByLabel(/^תאריך חזרה/).fill(RETURN);
  await page.getByLabel("תקציב", { exact: true }).fill("8000");
}

test("an estimate is ranked, saved, and found again in the history", async ({ page }) => {
  await fillDatesAndBudget(page);
  await page.getByRole("button", { name: "מצאו לי יעדים" }).click();

  const rows = page.getByRole("table").getByRole("row");
  await expect(rows.nth(1)).toContainText("ברצלונה");
  await expect(rows.nth(1)).toContainText("5,200 ₪"); // 2 x 300 + 7 x 100 = $1300
  await expect(rows.nth(2)).toContainText("רומא");
  await expect(rows.nth(2)).toContainText("5,360 ₪"); // 2 x 250 + 7 x 120 = $1340

  // Luxury: Barcelona 2 x 300 + 7 x 250 = $2350 = 9400 ILS, over the budget.
  await page.getByRole("button", { name: "מלון יוקרתי" }).click();
  await expect(page.getByText(/אין יעדים עם מחיר טיסה ומלון בתקציב שלך/)).toBeVisible();

  await page.getByRole("link", { name: "לדירוג השמור של החיפוש" }).click();
  await expect(page).toHaveURL(/\/history\/\d+$/);
  await expect(page.getByRole("table").getByRole("row").nth(1)).toContainText("ברצלונה");

  await page.getByRole("link", { name: "החיפושים שלי" }).click();
  await expect(page.getByRole("table").getByRole("row").nth(1)).toContainText("1.6.20308.6.20308,000 ₪");
});

test("a destination's view falls back to collected data and its date grid picks new dates", async ({ page }) => {
  await fillDatesAndBudget(page);
  await page.getByRole("button", { name: /יעד מסוים/ }).click();
  await page.getByLabel("לאן?").fill("ברצלונה, ספרד");
  await page.getByRole("button", { name: "הראו את היעד" }).click();

  await expect(page.getByRole("heading", { name: "ברצלונה, ספרד" })).toBeVisible();
  // Live search is off in these tests, so the view uses the collected price.
  await expect(page.getByText(/אין כרגע תשובה עדכנית, ולכן מוצגים מחירים שנאספו/)).toBeVisible();
  // The summary for the couple: 2 x $300 + 7 x $100 = $1300 = 5200 ILS.
  await expect(page.getByText("5,200 ₪", { exact: true })).toBeVisible();
  await expect(page.getByText("2,600 ₪ לאדם")).toBeVisible();
  await expect(page.getByText(/1 מתוך 1/)).toBeVisible();

  await expect(page.getByText(/יש לנו מחירים ל-4 מתוך 49 צירופי תאריכים/)).toBeVisible();
  // The cheapest flight on file nearby: $210 = 840 ILS, out 3 days later and back a day early.
  await page.getByRole("button", { name: /יציאה 4.6.2030, חזרה 7.6.2030: טיסה 840 ₪/ }).click();

  await expect(page).toHaveURL(/depart_date=2030-06-04&return_date=2030-06-07/);
  await expect(page.getByText(/4.6.2030 – 7.6.2030 \(3 לילות\)/)).toBeVisible();
  await expect(page.getByText("מלון, 3 לילות")).toBeVisible();
});

test("the data-quality page shows the gaps", async ({ page }) => {
  await page.goto("/data-quality");

  await expect(page.getByRole("row", { name: /^ברצלונה ספרד/ })).toContainText("היום");
  // Madrid has no data at all in these tests: a gap, not a zero price.
  await expect(page.getByRole("row", { name: /^מדריד ספרד/ })).toContainText("0--");
});
