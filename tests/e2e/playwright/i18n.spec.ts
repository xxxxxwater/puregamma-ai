import { expect, test } from "@playwright/test";

test.describe("localized routes", () => {
  test("/en landing renders English", async ({ page }) => {
    await page.goto("/en");
    await expect(page.getByRole("heading", { name: "Decide where to take Beta, where Alpha may exist, Long Gamma NAV 1 > 50." })).toBeVisible();
    await expect(page.getByText("AI SECONDARY-MARKET DECISION SUPPORT").first()).toBeVisible();
  });

  test("/zh landing renders Chinese", async ({ page }) => {
    await page.goto("/zh");
    await expect(page.getByRole("heading", { name: "判断何时承担 Beta、哪里可能存在 Alpha，Long Gamma NAV 1 > 50。" })).toBeVisible();
    await expect(page.getByText("面向二级市场的 AI 决策支持").first()).toBeVisible();
  });

  test("/en/onboarding/assets renders English onboarding", async ({ page }) => {
    await page.goto("/en/onboarding/assets");
    await expect(page.getByRole("heading", { name: "Choose assets to track" })).toBeVisible();
    await expect(page.getByText("选择需要跟踪的资产")).toHaveCount(0);
  });

  test("/zh/onboarding/assets renders Chinese onboarding", async ({ page }) => {
    await page.goto("/zh/onboarding/assets");
    await expect(page.getByRole("heading", { name: "选择需要跟踪的资产" })).toBeVisible();
    await expect(page.getByText("第 1 步 / 共 3 步")).toBeVisible();
  });

  test("/en/dashboard renders English labels", async ({ page }) => {
    await page.goto("/en/dashboard");
    await expect(page.getByRole("heading", { name: "PureGamma Intelligence Console" })).toBeVisible();
    await expect(page.getByText("Credit Balance")).toBeVisible();
  });

  test("/zh/dashboard renders Chinese labels", async ({ page }) => {
    await page.goto("/zh/dashboard");
    await expect(page.getByRole("heading", { name: "PureGamma 投研控制台" })).toBeVisible();
    await expect(page.getByText("Credits 余额")).toBeVisible();
  });

  test("language switcher preserves path and query params", async ({ page }) => {
    await page.goto("/en/portfolio?tab=risk");
    await page.getByRole("button", { name: "Switch language to Simplified Chinese" }).first().click();
    await expect(page).toHaveURL(/\/zh\/portfolio\?tab=risk$/);
  });

  test("missing translation fallback does not appear on rendered page", async ({ page }) => {
    await page.goto("/en/dashboard");
    await expect(page.getByText("Missing translation")).toHaveCount(0);
  });

  test("English route has no obvious Chinese UI text", async ({ page }) => {
    await page.goto("/en/billing");
    await expect(page.getByRole("heading", { name: "访问权限与订阅" })).toHaveCount(0);
    await expect(page.getByText("当前套餐")).toHaveCount(0);
  });

  test("Chinese route renders Chinese primary labels", async ({ page }) => {
    await page.goto("/zh/billing");
    await expect(page.getByRole("heading", { name: "访问权限与订阅" })).toBeVisible();
    await expect(page.getByText("当前套餐")).toBeVisible();
  });

  test("billing page localized", async ({ page }) => {
    await page.goto("/zh/billing");
    await expect(page.getByText("Credits 余额")).toBeVisible();
    await expect(page.getByRole("button", { name: /升级至 Pro/ })).toBeVisible();
  });

  test("daily push preview localized", async ({ page }) => {
    await page.goto("/zh/daily-push");
    await expect(page.getByRole("heading", { name: "每日研究推送" })).toBeVisible();
    await expect(page.getByText("PureGamma AI 每日简报").first()).toBeVisible();
  });

  test("portfolio partial data warning localized", async ({ page }) => {
    await page.goto("/zh/portfolio");
    await expect(page.getByRole("heading", { name: "组合净值 NAV" })).toBeVisible();
    await expect(page.getByText("至少同步两次后显示真实净值曲线")).toBeVisible();
  });

  test("Nautilus warning localized", async ({ page }) => {
    await page.goto("/zh/nautilus");
    await expect(page.getByRole("heading", { name: "策略运行控制台" })).toBeVisible();
    await expect(page.getByText("LIVE DISABLED")).toBeVisible();
  });

  test("metadata localized", async ({ page }) => {
    await page.goto("/zh");
    await expect(page).toHaveTitle("PureGamma AI - Beta、Alpha 与 Long Gamma AI 决策助手");
    const description = await page.locator("meta[name='description']").getAttribute("content");
    expect(description).toContain("二级市场 AI 决策支持");
  });
});
