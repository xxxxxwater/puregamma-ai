import { expect, test } from "@playwright/test";

test.describe("/billing", () => {
  test("shows plan cards and subscription controls", async ({ page }) => {
    await page.goto("/billing");

    await expect(page.getByRole("heading", { name: "Access & Subscription" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Manage Subscription/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Free" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Pro" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Max" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Enterprise" })).toBeVisible();
  });

  test("upgrade button calls checkout endpoint", async ({ page }) => {
    let called = false;
    await page.route("**/billing/create-checkout-session", async (route) => {
      called = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ checkout_url: "/en/billing/success", mode: "mock" }),
      });
    });

    await page.goto("/billing");
    await page.getByRole("button", { name: /Upgrade to Pro/i }).click({ noWaitAfter: true });

    await expect.poll(() => called).toBe(true);
  });

  test.fixme("shows insufficient credits copy when applicable", async () => {
    // Requires a frontend state/API contract for insufficient-credit billing copy.
  });
});
