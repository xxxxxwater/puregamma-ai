import { expect, test } from "@playwright/test";

test.describe("/nautilus", () => {
  test("shows live trading disabled guard and mock backtest results", async ({ page }) => {
    await page.goto("/nautilus");

    await expect(page.getByRole("heading", { name: "Strategy Runtime Console" })).toBeVisible();
    // "LIVE DISABLED" now appears twice by design: the console header badge and
    // the embedded LIVE safety panel, which (with no safety status) explains
    // that it treats the gate as disabled. Assert both instead of one ambiguous match.
    await expect(page.getByText("LIVE DISABLED")).toHaveCount(2);
    await expect(page.getByText("LIVE trading is disabled")).toBeVisible();
    await expect(page.getByText("Safety status is unavailable and treated as disabled; no executable LIVE trading entry is provided.")).toBeVisible();
    await expect(page.getByText("UNAVAILABLE", { exact: true })).toBeVisible();
    await expect(page.getByText("MOCK BRIDGE")).toBeVisible();
    await expect(page.getByRole("link", { name: "Strategies" })).toBeVisible();
  });
});
