import { expect, test, type Page } from "@playwright/test";

const primaryItemsEn = [
  { label: "Today", href: "/en/dashboard" },
  { label: "Agent Chat", href: "/en/chat" },
  { label: "NAV", href: "/en/portfolio" },
  { label: "Opportunities", href: "/en/opportunities" },
  { label: "Strategy", href: "/en/backtest" },
  { label: "Automation", href: "/en/daily-push" }
];

const primaryItemsZh = [
  { label: "今日", href: "/zh/dashboard" },
  { label: "Agent 对话", href: "/zh/chat" },
  { label: "NAV", href: "/zh/portfolio" },
  { label: "机会", href: "/zh/opportunities" },
  { label: "策略", href: "/zh/backtest" },
  { label: "自动化", href: "/zh/daily-push" }
];

const appPages = ["/en/dashboard", "/en/chat", "/en/portfolio", "/en/opportunities", "/en/backtest", "/en/daily-push"];

async function expectNoHorizontalScroll(page: Page) {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth))
    .toBeLessThanOrEqual(1);
}

test.describe("mobile bottom navigation @375px", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("shows exactly the 6 primary items (en) and each navigates", async ({ page }) => {
    await page.goto("/en/dashboard");
    const bottomNav = page.locator('nav[aria-label="Primary navigation"]');
    await expect(bottomNav).toBeVisible();
    await expect(bottomNav.getByRole("link")).toHaveCount(6);
    for (const item of primaryItemsEn) {
      const link = bottomNav.getByRole("link", { name: item.label, exact: true });
      await expect(link).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(new RegExp(`${item.href}$`));
    }
  });

  test("shows exactly the 6 primary items (zh) and each navigates", async ({ page }) => {
    await page.goto("/zh/dashboard");
    const bottomNav = page.locator('nav[aria-label="主导航"]');
    await expect(bottomNav).toBeVisible();
    await expect(bottomNav.getByRole("link")).toHaveCount(6);
    for (const item of primaryItemsZh) {
      const link = bottomNav.getByRole("link", { name: item.label, exact: true });
      await expect(link).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(new RegExp(`${item.href}$`));
    }
  });

  test("chat page exposes conversation history drawer and voice entry", async ({ page }) => {
    await page.goto("/en/chat");
    const historyButton = page.getByRole("button", { name: "Conversation history" });
    await expect(historyButton).toBeVisible();
    const voiceEntry = page.getByRole("link", { name: "Voice Secretary" });
    await expect(voiceEntry).toBeVisible();
    await expect(voiceEntry).toHaveAttribute("href", /\/en\/secretary$/);

    await historyButton.click();
    const drawer = page.getByRole("dialog", { name: "Conversation history" });
    await expect(drawer).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
  });

  test("daily-push page exposes automation sections and the multi-channel contract", async ({ page }) => {
    await page.goto("/en/daily-push");
    const sectionsNav = page.locator('nav[aria-label="Automation sections"]');
    for (const label of ["Daily report", "Channels", "Alerts", "Deliveries", "Autopilot"]) {
      await expect(sectionsNav.getByRole("link", { name: label, exact: true })).toBeVisible();
    }
    const channelsCard = page.locator("#channels");
    await expect(channelsCard.getByRole("button", { name: "Email", exact: true })).toBeEnabled();
    for (const channel of ["Telegram", "Slack", "iMessage"]) {
      await expect(channelsCard.getByRole("button", { name: new RegExp(channel) })).toBeVisible();
    }
    const dailyCard = page.locator("#daily");
    for (const reportType of ["Crypto daily", "US equities daily", "Week-ahead events", "Portfolio daily"]) {
      await expect(dailyCard.getByRole("button", { name: reportType, exact: true })).toBeVisible();
    }
    await expect(page.locator("#alerts")).toBeVisible();
    await expect(page.locator("#deliveries")).toBeVisible();
    await expect(page.locator("#autopilot")).toBeVisible();

    await page.goto("/zh/daily-push");
    const sectionsNavZh = page.locator('nav[aria-label="自动化小节"]');
    for (const label of ["日报", "渠道", "提醒", "投递记录", "Autopilot"]) {
      await expect(sectionsNavZh.getByRole("link", { name: label, exact: true })).toBeVisible();
    }
  });

  test("primary app pages have no page-level horizontal scroll", async ({ page }) => {
    for (const path of appPages) {
      await page.goto(path);
      await expectNoHorizontalScroll(page);
    }
  });
});

test.describe("responsive chrome", () => {
  test("sidebar and bottom bar are mutually exclusive across breakpoints", async ({ page }) => {
    await page.goto("/en/dashboard");
    const bottomNav = page.locator('nav[aria-label="Primary navigation"]');
    const sidebar = page.locator("aside").first();

    await page.setViewportSize({ width: 375, height: 812 });
    await expect(bottomNav).toBeVisible();
    await expect(sidebar).toBeHidden();
    await expectNoHorizontalScroll(page);

    await page.setViewportSize({ width: 768, height: 1024 });
    await expect(bottomNav).toBeVisible();
    await expect(sidebar).toBeHidden();
    await expectNoHorizontalScroll(page);

    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(bottomNav).toBeHidden();
    await expect(sidebar).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  test("chat renders without horizontal scroll at 768 and 1440", async ({ page }) => {
    await page.goto("/en/chat");
    const bottomNav = page.locator('nav[aria-label="Primary navigation"]');

    await page.setViewportSize({ width: 768, height: 1024 });
    await expectNoHorizontalScroll(page);

    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(bottomNav).toBeHidden();
    await expectNoHorizontalScroll(page);
  });
});
