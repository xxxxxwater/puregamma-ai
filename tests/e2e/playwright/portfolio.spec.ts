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
});
