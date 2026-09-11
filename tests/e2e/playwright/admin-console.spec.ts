import { expect, test, type Page } from "@playwright/test";

/**
 * Admin console acceptance.
 *
 * What this suite can prove without an administrator session:
 *   - the section is behind the admin guard, and a non-admin gets the
 *     permission state rather than the console;
 *   - the section navigation exists, marks the current page, and is localized;
 *   - every admin surface renders an explicit failure state instead of a
 *     plausible-looking zero when its read does not succeed.
 *
 * What it cannot prove, and does not claim: the console's own numbers. Those
 * reads run in the Next server process (`app/[locale]/admin/page.tsx` is a
 * Server Component), so a browser-level `page.route` cannot intercept them —
 * they never pass through the page. Rendering them against fixtures would
 * require either a second server or moving the reads client-side. The live pass
 * needs an administrator session; see the handoff notes.
 */

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

const ADMIN_USER = {
  user: {
    id: "u-admin",
    email: "admin@example.invalid",
    name: "Admin Fixture",
    role: "admin",
    plan: "Enterprise",
    credit_balance: 0,
    auth_provider: "email",
  },
};

/**
 * Answer the reads the shell performs on every authenticated page.
 *
 * An un-stubbed call on one of these returns 401, and `lib/api.ts` treats a 401
 * on an authenticated route as an expired session: the watchdog then replaces
 * the page with `/login?returnTo=...`. A missed stub therefore looks like a
 * redirect rather than a missing fixture.
 *
 * Registration order matters: Playwright consults routes most-recently-added
 * first, so the broad `/admin/**` fallback goes FIRST and the specific routes
 * below it win. Registering the fallback last silently shadows every one of
 * them.
 */
async function stubShell(page: Page, role: "admin" | "user" = "admin") {
  await page.route(`${API}/admin/**`, (route) => {
    const url = route.request().url();
    if (/\/admin\/billing\/accounts\/[^/?]+$/.test(url)) {
      return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) });
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({}) });
  });
  await page.route(`${API}/me`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { ...ADMIN_USER.user, role } }) }),
  );
  await page.route(`${API}/api/frontend/plugins*`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ plugins: [], capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 } }),
    }),
  );
  await page.route(`${API}/auth/x/config`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ x_login_enabled: false }) }),
  );
  // The credit console and the user table read client-side, so these are
  // stubbable and must answer 200 — an unstubbed 401 would trip the watchdog.
  await page.route(`${API}/admin/billing/accounts**`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ accounts: [], total: 0, limit: 50, offset: 0 }) }),
  );
  await page.route(`${API}/admin/users**`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ users: [], total: 0, limit: 25, offset: 0, has_more: false }) }),
  );
}

test.describe("admin section", () => {
  test("a non-administrator gets the permission state, not the console", async ({ page }) => {
    await stubShell(page, "user");
    await page.goto("/zh/admin");
    await expect(page.getByText("需要管理员权限")).toBeVisible();
    // The console content must not leak behind the guard.
    await expect(page.getByRole("navigation", { name: "管理后台分区" })).toHaveCount(0);
  });

  test("the section navigation is present, localized and marks the current page", async ({ page }) => {
    await stubShell(page);
    await page.goto("/zh/admin");
    const nav = page.getByRole("navigation", { name: "管理后台分区" });
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link", { name: "总览" })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "API Gateway" })).toHaveAttribute("href", "/zh/admin/gateway");
    await expect(nav.getByRole("link", { name: "支付意图" })).toHaveAttribute("href", "/zh/admin/billing-intents");
    await expect(nav.getByRole("link", { name: "Stripe 事件" })).toHaveAttribute("href", "/zh/admin/stripe-events");
  });

  test("English section navigation is localized", async ({ page }) => {
    await stubShell(page);
    await page.goto("/en/admin");
    await expect(page).toHaveURL(/\/en\/admin$/);
    const nav = page.getByRole("navigation", { name: "Admin sections" });
    await expect(nav.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "Payment intents" })).toHaveAttribute("href", "/en/admin/billing-intents");
  });

  test("a failed admin read renders an explicit failure, never a healthy zero", async ({ page }) => {
    // This environment has no administrator session, so the server-side reads
    // fail and the page must say so. That is the same code path a real outage
    // takes, which is what makes it worth pinning.
    await stubShell(page);
    await page.goto("/zh/admin");
    await expect(page).toHaveURL(/\/zh\/admin$/);

    // The top-level state names the cause instead of showing the console as if
    // it were fine.
    await expect(page.getByText("需要管理员权限").first()).toBeVisible();
    // Every count that could not be read shows an explicit placeholder, not 0.
    await expect(page.getByText("—").first()).toBeVisible();
    // Each panel reports its own failure rather than an empty-but-normal view.
    await expect(page.getByText("运行状态读取失败。")).toBeVisible();
    await expect(page.getByText("任务队列读取失败。")).toBeVisible();
    // The user table owns its own read (it is the client-side pager), so it does
    // not inherit the server's failure: it shows the answer it actually got,
    // which here is a successful empty page.
    await expect(page.getByTestId("admin-users-count")).toHaveText("0");
    await expect(page.getByTestId("admin-users-error")).toHaveCount(0);
    // And it must not offer stale "mock state" language.
    await expect(page.getByText("Mock 运营状态")).toHaveCount(0);
  });

  test("the user table queries the server for filters and pages", async ({ page }) => {
    // The list is paginated server-side, so filtering must reach the API. A
    // client-side filter over the current page would answer a search with a
    // slice of a larger result set while looking like a full answer.
    //
    // Registered AFTER `stubShell`: Playwright consults routes in reverse
    // registration order, so this one must come last to win.
    const calls: string[] = [];
    await stubShell(page);
    await page.route(`${API}/admin/users**`, (route) => {
      const url = new URL(route.request().url());
      const q = url.searchParams.get("q") || "";
      const offset = Number(url.searchParams.get("offset") || 0);
      calls.push(`q=${q} offset=${offset}`);
      // Two pages of one row each.
      const rows = offset === 0
        ? [{ id: "u1", email: "alice@example.com", plan: "Pro", role: "user", membership_tier: "gold" }]
        : [{ id: "u2", email: "bob@example.com", plan: "Free", role: "user", membership_tier: "bronze" }];
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ users: rows, total: 40, limit: 25, offset, page: offset / 25 + 1, has_more: offset === 0 }),
      });
    });
    await page.goto("/zh/admin");
    await expect(page).toHaveURL(/\/zh\/admin$/);

    // The server total is what the header reports, not the page length.
    await expect(page.getByTestId("admin-users-count")).toHaveText("40");
    await expect(page.getByText("第 1 / 2 页")).toBeVisible();

    // Next page issues a new server query.
    await page.getByRole("button", { name: /下一页/ }).click();
    await expect(page.getByText("第 2 / 2 页")).toBeVisible();
    expect(calls.some((call) => call.includes("offset=25"))).toBe(true);

    // A filter is a server query too.
    await page.getByPlaceholder("例如 alice@example.com").fill("alice");
    await expect.poll(() => calls.some((call) => call.includes("q=alice")), { timeout: 5000 }).toBe(true);
  });

  test("the Gateway console keeps its page and shares the section nav", async ({ page }) => {
    await stubShell(page);
    await page.route(`${API}/admin/gateway/**`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ providers: [], registered_plugins: [], revisions: [], syncs: [], revenue_usd: "0", provider_cost_usd: "0", profit_usd: "0", prepaid_liability_usd: "0", requests: 0 }) }),
    );
    await page.goto("/zh/admin/gateway");
    await expect(page).toHaveURL(/\/zh\/admin\/gateway$/);
    const nav = page.getByRole("navigation", { name: "管理后台分区" });
    await expect(nav.getByRole("link", { name: "API Gateway" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "API Gateway 管理" })).toBeVisible();
  });
});
