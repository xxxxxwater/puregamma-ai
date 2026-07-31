import { expect, test } from "@playwright/test";

test.describe("MSTR–BTC dashboard", () => {
  test("shows source provenance, safe unavailable state, scenario inputs, and Agent handoff", async ({ page }) => {
    await page.goto("/en/opportunities/mstr-btc");

    await expect(page.getByRole("heading", { name: "MSTR–BTC Dashboard" })).toBeVisible();
    await expect(page.getByText("Live data source: Strategy.com")).toBeVisible();
    await expect(page.getByText("Reserves & capital structure")).toBeVisible();
    await expect(page.getByText("Scenario assumptions")).toBeVisible();
    await expect(page.getByText("No verified time series is available for this view.").first()).toBeVisible();
    await page.getByLabel(/BTC price assumption/).fill("100000");
    await expect(page.getByRole("link", { name: /Ask Agent:/ }).first()).toHaveAttribute("href", /prompt=/);
  });

  test("keeps the research view inside the mobile viewport", async ({ page }) => {
    await page.goto("/en/opportunities/mstr-btc");

    await expect(page.getByRole("heading", { name: "MSTR–BTC Dashboard" })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByLabel(/BTC price assumption/)).toBeVisible();
  });
});
