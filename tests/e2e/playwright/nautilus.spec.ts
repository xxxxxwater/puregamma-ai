import { expect, test } from "@playwright/test";

test.describe("/nautilus", () => {
  test("shows live trading disabled guard and mock backtest results", async ({ page }) => {
    await page.goto("/nautilus");

    await expect(page.getByRole("heading", { name: "Strategy Research Lab" })).toBeVisible();
    await expect(page.getByText("Live trading is disabled by default.", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Run mock backtest" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Backtest Results" })).toBeVisible();
    await expect(page.getByText("Sharpe")).toBeVisible();
    await expect(page.getByText("Max Drawdown")).toBeVisible();
    await expect(page.getByText("NAUTILUS_LIVE_TRADING_ENABLED=false")).toBeVisible();
    await expect(page.getByText("NAUTILUS_ALLOW_LIVE_ORDER=false")).toBeVisible();
  });
});
