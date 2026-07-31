import { expect, test } from "@playwright/test";

test.describe("/daily-push", () => {
  test("shows iMessage preference, entitlement requirement, test send, and disclaimer", async ({ page }) => {
    await page.goto("/daily-push");

    await expect(page.getByRole("heading", { name: "Daily Research Delivery" })).toBeVisible();
    await expect(page.getByLabel("Channel")).toHaveValue("iMessage");
    await expect(page.getByText("Daily iMessage delivery is available on Max and Enterprise plans.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send test push" })).toBeVisible();
    await expect(page.getByText("Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.")).toBeVisible();
    await expect(page.getByText("KOL sentiment is an input, not a verified fact.").first()).toBeVisible();
  });
});
