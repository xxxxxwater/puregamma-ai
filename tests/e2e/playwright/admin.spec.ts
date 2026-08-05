import { expect, test } from "@playwright/test";

test.describe("/admin", () => {
  test("shows a non-admin denied state without operational modules", async ({ page }) => {
    await page.goto("/admin");

    await expect(page.getByText("Administrator access required")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Users", exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Stripe webhook events", exact: true })).toHaveCount(0);
  });
});
