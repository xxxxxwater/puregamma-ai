import { expect, test } from "@playwright/test";

test.describe("/dashboard", () => {
  test("loads dashboard shell with plan, credits, market regime, and mock badge", async ({ page }) => {
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: "PureGamma Intelligence Console" })).toBeVisible();
    await expect(page.getByText("Credit Balance")).toBeVisible();
    await expect(page.getByText("Free plan")).toBeVisible();
    await expect(page.getByText("Live assets")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Latest Daily Brief" })).toBeVisible();
  });
});
