import { expect, test } from "@playwright/test";

test.describe("/portfolio", () => {
  test("shows NAV, allocation, partial warning, and sync entrypoint", async ({ page }) => {
    await page.goto("/portfolio");

    await expect(page.getByRole("heading", { name: "Portfolio NAV" })).toBeVisible();
    await expect(page.getByText("The real NAV curve appears after at least two syncs")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Plaid Investments" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Interactive Brokers" })).toBeVisible();
  });

  test("shows read-only connection entrypoints", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.getByRole("button", { name: "Connect Plaid" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Connect IBKR" })).toBeDisabled();
  });

  for (const { label, observationAge, collectorStale } of [
    { label: "an older observation is republished", observationAge: 300, collectorStale: false },
    { label: "the collector flags a recent observation", observationAge: 10, collectorStale: true },
  ]) {
    test(`marks PM data stale when ${label}`, async ({ page }) => {
      const now = Date.now();
      await page.clock.setFixedTime(now);
      await page.route("**/me", (route) => route.fulfill({
        json: { user: { id: "review-user", email: "review@example.com", name: "Review User", role: "user", plan: "Free", credit_balance: 10 } },
      }));
      await page.route("**/portfolio/pm", (route) => route.fulfill({
        json: {
          available: true,
          stale: collectorStale,
          data_as_of: new Date(now - observationAge * 1_000).toISOString(),
          generated_at: new Date(now).toISOString(),
          account: { account_equity_usd: "100.00" },
        },
      }));
      await page.route("**/portfolio/pm/history", (route) => route.fulfill({ json: { available: false, points: [] } }));

      await page.goto("/en/portfolio");

      await expect(page.getByText("Portfolio Margin", { exact: true })).toBeVisible();
      await expect(page.getByText("STALE", { exact: true })).toBeVisible();
    });
  }
});
