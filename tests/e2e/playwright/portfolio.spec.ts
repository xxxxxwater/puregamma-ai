import { expect, test, type Page } from "@playwright/test";

/**
 * /portfolio with no portfolio data (every API read is a 503 outage).
 *
 * The connect buttons used to be asserted as disabled. They are deliberately
 * enabled now: when Plaid is not configured the card says "NEEDS CONFIG" and a
 * click explains why the connection cannot open, without calling the
 * link-token endpoint or pretending a connection started.
 */
async function offline(page: Page) {
  await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
  await page.route("**/__dev-api/me", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u-pf", email: "pf@example.invalid", name: "Portfolio", role: "user", plan: "Pro", credit_balance: 10, auth_provider: "email" } }) }),
  );
}

test.describe("/portfolio", () => {
  test.beforeEach(async ({ page }) => offline(page));

  test("shows NAV, the empty-history notice and the connection entrypoints", async ({ page }) => {
    await page.goto("/en/portfolio");

    await expect(page.getByRole("heading", { name: "Portfolio NAV" })).toBeVisible();
    await expect(page.getByText("The real NAV curve appears after at least two syncs")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Plaid Investments" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Interactive Brokers" })).toBeVisible();
  });

  test("an unconfigured Plaid connection explains itself instead of opening", async ({ page }) => {
    let linkTokenRequests = 0;
    await page.route("**/__dev-api/portfolio/plaid/link-token", (route) => { linkTokenRequests += 1; return route.abort(); });
    await page.goto("/en/portfolio");

    await expect(page.getByText("NEEDS CONFIG").first()).toBeVisible();
    await page.getByRole("button", { name: "Connect Plaid" }).click();
    await expect(page.getByText("Plaid Production is missing its Production Secret, so account connection cannot open yet.")).toBeVisible();
    await page.getByRole("button", { name: "Connect IBKR with Plaid" }).click();
    await expect(page.getByText("Plaid Production is missing its Production Secret, so account connection cannot open yet.")).toBeVisible();
    expect(linkTokenRequests).toBe(0);
  });
});
