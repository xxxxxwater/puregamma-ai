import { expect, test } from "@playwright/test";

test.describe("/dashboard", () => {
  test("loads the Today decision console without inventing unavailable data", async ({ page }) => {
    await page.goto("/en/dashboard");

    await expect(page.getByRole("heading", { name: "Decide what matters today." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Overnight key events" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "My portfolio impact" })).toBeVisible();
    await expect(page.getByPlaceholder("Ask PureGamma about today's decisions…")).toBeVisible();
  });
});
