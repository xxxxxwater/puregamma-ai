import { expect, test } from "@playwright/test";

test.describe("/portfolio", () => {
  test("shows NAV, allocation, partial warning, and sync entrypoint", async ({ page }) => {
    await page.goto("/portfolio");

    await expect(page.getByRole("heading", { name: "Portfolio NAV Review" })).toBeVisible();
    await expect(page.getByText("02 / Portfolio NAV")).toBeVisible();
    await expect(page.getByText("Partial data. NAV is based only on currently synced sources.").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Allocation" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Sync All Sources" })).toBeVisible();
  });

  test("sync all opens integrations mock flow", async ({ page }) => {
    await page.goto("/portfolio");
    await page.getByRole("link", { name: "Sync All Sources" }).click();

    await expect(page).toHaveURL(/\/en\/integrations$/);
    await expect(page.getByRole("heading", { name: "Portfolio Source Connections" })).toBeVisible();
  });
});
