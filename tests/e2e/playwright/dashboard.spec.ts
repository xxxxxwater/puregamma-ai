import { expect, test } from "@playwright/test";

/**
 * The dashboard is server-rendered from the market snapshot, subscription and
 * reports. In the suite those server reads hit the offline fixture API
 * (fixtures/ssr-api.mjs), which answers 503: the page must render its waiting
 * and unavailable states and never invent a thesis, a balance or live data.
 *
 * (This spec used to look for "Decide what matters today." and an "Overnight
 * key events" panel from an earlier dashboard that no longer exists.)
 */
test.describe("/dashboard", () => {
  test("renders the console without inventing unavailable data (en)", async ({ page }) => {
    await page.goto("/en/dashboard");

    await expect(page.getByRole("heading", { name: "Market intelligence, in motion." })).toBeVisible();
    // No market data: the status says it is waiting rather than claiming live.
    await expect(page.getByText("WAITING").first()).toBeVisible();
    await expect(page.getByText("Account and billing data unavailable")).toBeVisible();
    // No fresh brief: an explicit empty state, not a placeholder thesis.
    await expect(page.getByText("No research brief")).toBeVisible();
    await expect(page.getByText("Today's decisions")).toBeVisible();
  });

  test("renders the console without inventing unavailable data (zh)", async ({ page }) => {
    await page.goto("/zh/dashboard");

    await expect(page.getByRole("heading", { name: "市场智能，正在演化。" })).toBeVisible();
    await expect(page.getByText("等待数据").first()).toBeVisible();
    await expect(page.getByText("账户与计费数据暂不可用")).toBeVisible();
    await expect(page.getByText("暂无研究简报")).toBeVisible();
  });
});
