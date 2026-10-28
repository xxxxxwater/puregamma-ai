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

  // The contract (apps/web/lib/api.ts): a 402 / INSUFFICIENT_CREDITS answer
  // sends the user to billing in their own locale; there is no separate copy.
  test("running out of credits on a chat send lands on billing in the user's locale", async ({ page }) => {
    const user = { user: { id: "u-billing", email: "billing@example.invalid", name: "Billing", role: "user", plan: "Free", credit_balance: 0, auth_provider: "email" } };
    const conversation = { id: "c-billing", title: "Credits", status: "active", archived_at: null, created_at: "2026-10-28T08:00:00+00:00", updated_at: "2026-10-28T08:00:00+00:00" };
    const quota = { plan: "Free", used: 0, limit: 10, remaining: 10, concurrent_limit: 1, running: 0, credit_balance: 0 };
    await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
    await page.route("**/__dev-api/me", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(user) }));
    await page.route("**/__dev-api/api/agent/capabilities", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({
      capabilities: { plan: "Free", allowed_data_sources: [], allowed_skills: [], max_attachments: 1 }, quota,
      models: [{ id: "default", display_name: "Default model", description: "", provider: "deepseek", available: true, reason: null, credit_cost: null }],
      skills: [], plugins: [], plugin_counts: { total: 0, enabled: 0, tools: 0 },
    }) }));
    await page.route("**/__dev-api/api/agent/quota", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(quota) }));
    await page.route("**/__dev-api/api/agent/conversations", (route) => route.request().method() === "POST"
      ? route.fulfill({ contentType: "application/json", body: JSON.stringify({ conversation }) })
      : route.fulfill({ contentType: "application/json", body: JSON.stringify({ conversations: [] }) }));
    await page.route("**/__dev-api/api/agent/conversations/*/messages", (route) =>
      route.fulfill({ status: 402, contentType: "application/json", body: JSON.stringify({ detail: { code: "INSUFFICIENT_CREDITS", message: "Not enough credits." } }) }));

    await page.goto("/zh/chat");
    await expect(page).toHaveURL(/\/zh\/chat$/);
    await page.getByTestId("chat-composer-input").fill("BTC 现在怎么样");
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/zh\/billing$/);
    await expect(page.getByRole("heading", { name: "访问权限与订阅" })).toBeVisible();
  });
});
