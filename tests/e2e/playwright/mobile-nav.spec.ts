import { expect, test, type Page } from "@playwright/test";

/**
 * Small-screen navigation as the app actually ships it.
 *
 * This spec used to describe a six-item bottom navigation bar and a "Voice
 * Secretary" link on the chat page; neither exists. Below `lg` the primary
 * navigation is a drawer opened from the header's menu button (a dialog named
 * "Primary navigation" only while open), the desktop rail is hidden, and the
 * chat history is a drawer that is a dialog named "Conversation history" only
 * while open. Every API call is stubbed; anything unlisted is a 503 outage.
 */

const USER = {
  user: { id: "u-mobile-nav", email: "mobile-nav@example.invalid", name: "Mobile Nav", role: "user", plan: "Pro", credit_balance: 100, auth_provider: "email" },
};

async function stubApi(page: Page) {
  // Registered first, so the specific stubs below take precedence.
  await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
  await page.route("**/__dev-api/me", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(USER) }));
  await page.route("**/__dev-api/api/agent/conversations", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ conversations: [{ id: "c1", title: "BTC review", status: "active", archived_at: null, created_at: "2026-10-28T08:00:00+00:00", updated_at: "2026-10-28T08:00:00+00:00" }] }) }),
  );
}

async function expectNoHorizontalScroll(page: Page) {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth))
    .toBeLessThanOrEqual(1);
}

const primaryEn = [
  { label: "Dashboard", href: "/en/dashboard" },
  { label: "Agent Chat", href: "/en/chat" },
  { label: "NAV", href: "/en/portfolio" },
  { label: "Backtest", href: "/en/backtest" },
  { label: "Private Secretary", href: "/en/secretary" },
];

const primaryZh = [
  { label: "控制台", href: "/zh/dashboard" },
  { label: "Agent 对话", href: "/zh/chat" },
  { label: "回测", href: "/zh/backtest" },
  { label: "亲密秘书", href: "/zh/secretary" },
];

test.describe("phone navigation drawer @375px", () => {
  test.use({ viewport: { width: 375, height: 812 } });
  test.beforeEach(async ({ page }) => stubApi(page));

  for (const [locale, items, dialogName, menuName] of [
    ["en", primaryEn, "Primary navigation", "Open navigation"],
    ["zh", primaryZh, "主导航", "打开导航"],
  ] as const) {
    test(`the menu opens the primary navigation and each item navigates (${locale})`, async ({ page }) => {
      await page.goto(`/${locale}/dashboard`);
      // No rail on a phone: the drawer is the navigation.
      await expect(page.locator("aside.shell-rail")).toBeHidden();
      for (const item of items) {
        const menu = page.getByRole("button", { name: menuName });
        await menu.click();
        const drawer = page.getByRole("dialog", { name: dialogName });
        await expect(drawer).toBeVisible();
        await drawer.getByRole("link", { name: item.label, exact: true }).click();
        await expect(page).toHaveURL(new RegExp(`${item.href}$`));
        // Choosing a destination closes the drawer.
        await expect(page.getByRole("dialog", { name: dialogName })).toHaveCount(0);
      }
    });
  }

  test("the chat history drawer is a dialog only while open and closes on Escape", async ({ page }) => {
    await page.goto("/en/chat");
    await expect(page).toHaveURL(/\/en\/chat$/);
    await expect(page.getByRole("dialog", { name: "Conversation history" })).toHaveCount(0);
    const trigger = page.getByRole("button", { name: "Conversation history" });
    await expect(trigger).toBeVisible();
    await trigger.click();
    const drawer = page.getByRole("dialog", { name: "Conversation history" });
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText("BTC review");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Conversation history" })).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("primary app pages have no page-level horizontal scroll", async ({ page }) => {
    for (const path of ["/en/dashboard", "/en/chat", "/en/portfolio", "/en/backtest", "/en/secretary", "/en/daily-push"]) {
      await page.goto(path);
      await expectNoHorizontalScroll(page);
    }
  });
});

test.describe("responsive chrome", () => {
  test.beforeEach(async ({ page }) => stubApi(page));

  test("the rail and the menu button are mutually exclusive across breakpoints", async ({ page }) => {
    await page.goto("/en/dashboard");
    const menu = page.getByTestId("nav-menu-button");
    const rail = page.locator("aside.shell-rail");

    for (const viewport of [{ width: 375, height: 812 }, { width: 768, height: 1024 }]) {
      await page.setViewportSize(viewport);
      await expect(menu).toBeVisible();
      await expect(rail).toBeHidden();
      await expectNoHorizontalScroll(page);
    }

    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(menu).toBeHidden();
    await expect(rail).toBeVisible();
    await expect(rail.getByRole("link", { name: "Agent Chat", exact: true })).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  test("chat renders without horizontal scroll at 768 and 1440", async ({ page }) => {
    await page.goto("/en/chat");
    await page.setViewportSize({ width: 768, height: 1024 });
    await expectNoHorizontalScroll(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.getByTestId("nav-menu-button")).toBeHidden();
    await expectNoHorizontalScroll(page);
  });
});
