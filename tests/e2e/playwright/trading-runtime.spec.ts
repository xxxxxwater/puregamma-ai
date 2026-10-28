import { expect, test, type Page } from "@playwright/test";

/**
 * PAPER/SHADOW runtime console (Nautilus): missing data is never shown as $0
 * and fractions render without binary-float noise. Every endpoint is stubbed.
 */

const strategy = {
  id: "s1", name: "BTC 1h momentum", description: "draft", status: "draft", current_version: 1, execution_mode: "PAPER",
  draft: { instruments: ["BTCUSDT"], venues: ["MOCK"], timeframe: "1h", strategy_type: "trend", sentiment_sources: [], max_notional: 1000, leverage: 1, max_daily_loss: 50, max_drawdown: 0.07 },
  latest_run: null, created_at: "2026-10-28T00:00:00Z", updated_at: "2026-10-28T00:00:00Z",
};

async function stub(page: Page, { performance }: { performance: "down" | "ok" }) {
  await page.route("**/__dev-api/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/__dev-api/, "");
    if (path === "/me") return route.fulfill({ json: { user: { id: "u", email: "u@example.invalid", name: "U", role: "user", plan: "Pro", credit_balance: 1 } } });
    if (path === "/strategies") return route.fulfill({ json: { strategies: [strategy] } });
    if (path === "/trading/accounts") return route.fulfill({ json: { accounts: [] } });
    if (path === "/trading/positions") return route.fulfill({ json: { positions: [] } });
    if (path === "/trading/orders") return route.fulfill({ json: { orders: [] } });
    if (path === "/trading/performance") {
      return performance === "down" ? route.fulfill({ status: 503, json: { detail: "unavailable" } }) : route.fulfill({ json: { accounts: [{ equity: 10250.5, daily_pnl: -12.25, exposure: 2000, available_margin: 8000, stale: false, captured_at: new Date().toISOString() }] } });
    }
    return route.fulfill({ status: 503, json: { detail: "unavailable" } });
  });
}

test("an unavailable paper account is shown as not loaded, never as $0", async ({ page }) => {
  await stub(page, { performance: "down" });
  await page.goto("/en/trading/positions");
  await expect(page.getByTestId("paper-performance-unavailable")).toBeVisible();
  await expect(page.getByText("$0", { exact: true })).toHaveCount(0);
});

test("a loaded paper account shows its figures", async ({ page }) => {
  await stub(page, { performance: "ok" });
  await page.goto("/en/trading/positions");
  await expect(page.getByText("$10,250.5")).toBeVisible();
  await expect(page.getByTestId("paper-performance-unavailable")).toHaveCount(0);
});

test("strategy drawdown renders without float noise", async ({ page }) => {
  await stub(page, { performance: "ok" });
  await page.goto("/en/trading/risk");
  await expect(page.getByText(/DD 7%/)).toBeVisible();
  await expect(page.getByText(/7\.0000/)).toHaveCount(0);
});
