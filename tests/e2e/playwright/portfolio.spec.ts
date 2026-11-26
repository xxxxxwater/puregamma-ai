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

  const balance = { asset: "BTC", is_liability: true, value_usd: "-800", unrealized_pnl: "0.01", price_usd: "80000" };
  const usd = { asset: "USDT", is_liability: false, value_usd: "100", unrealized_pnl: "-3", price_usd: "1" };
  for (const scenario of [
    { label: "withholds PnL without a USD denomination", balances: [balance, usd], account: {}, pnl: "--", liability: "$800.00" },
    { label: "withholds totals for missing valuations", balances: [{ ...balance, value_usd: null, price_usd: null }, usd], account: {}, pnl: "--", liability: "--" },
    { label: "withholds liabilities for a partial snapshot", balances: [balance], partial: true, account: { total_unrealized_pnl_usd: "22.00" }, pnl: "$22.00", liability: "--" },
    { label: "preserves a reported zero", balances: [], account: { total_unrealized_pnl_usd: "0" }, pnl: "$0.00", liability: "--" },
    { label: "shows zero liabilities for a valued asset-only book", balances: [usd], account: { total_unrealized_pnl_usd: "-3.00" }, pnl: "-$3.00", liability: "$0.00" },
  ]) {
    test(`PM account ${scenario.label}`, async ({ page }) => {
      await page.route("**/__dev-api/portfolio/pm", (route) => route.fulfill({
        json: { available: true, partial: scenario.partial, balances: scenario.balances, account: scenario.account },
      }));
      await page.goto("/en/portfolio");

      await expect(page.locator("dt").filter({ hasText: /^Unrealized PnL$/ }).locator("..").locator("dd")).toHaveText(scenario.pnl);
      await expect(page.getByText("Liabilities", { exact: true }).locator("..").locator("div").nth(1)).toHaveText(scenario.liability);
    });
  }

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
