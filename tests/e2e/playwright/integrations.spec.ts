import { expect, test } from "@playwright/test";

test.describe("/integrations", () => {
  test("shows Plaid, exchange read-only warning, wallet flow, and notification integration", async ({ page }) => {
    await page.goto("/integrations");

    await expect(page.getByRole("heading", { name: "Portfolio Source Connections" })).toBeVisible();
    await expect(page.getByText("Use read-only API keys only.").first()).toBeVisible();
    await expect(page.getByText("Never provide withdrawal permissions or private keys.").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Plaid Brokerage" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Binance Read-only" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Telegram" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "iMessage" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect" }).first()).toBeVisible();
  });
});
