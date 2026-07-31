import { expect, test } from "@playwright/test";

test.describe("/nautilus", () => {
  test("shows live trading disabled guard and mock backtest results", async ({ page }) => {
    await page.goto("/nautilus");

    await expect(page.getByRole("heading", { name: "Strategy Runtime Console" })).toBeVisible();
    await expect(page.getByText("LIVE DISABLED")).toBeVisible();
    await expect(page.getByText("UNAVAILABLE", { exact: true })).toBeVisible();
    await expect(page.getByText("MOCK BRIDGE")).toBeVisible();
    await expect(page.getByRole("link", { name: "Strategies" })).toBeVisible();
  });
});
