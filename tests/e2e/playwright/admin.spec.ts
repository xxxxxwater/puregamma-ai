import { expect, test } from "@playwright/test";

test.describe("/admin", () => {
  test("shows non-admin denied state and admin operational sections", async ({ page }) => {
    await page.goto("/admin");

    await expect(page.getByRole("heading", { name: "Operational Control Room" })).toBeVisible();
    await expect(page.getByText("Access control active")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Stripe webhook events" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Notification deliveries" })).toBeVisible();
  });
});
