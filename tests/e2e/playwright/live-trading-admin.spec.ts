import { expect, test, type Page } from "@playwright/test";

/**
 * Admin LIVE review (frontend only; every endpoint is stubbed).
 *
 * - a non-administrator sees the access notice and the page calls no admin
 *   trading endpoint; a server 403 is shown as a refusal, not as "empty";
 * - engaging/releasing a kill switch, deciding eligibility and marking a
 *   reconciliation reviewed all need a reason and a typed confirmation, and
 *   send exactly what the dialog stated;
 * - a failed read says "could not be read", never "nothing to show".
 */

type Call = { method: string; path: string; body: unknown };

const active = { id: "ks1", scope: "global", scope_id: null, state: "active", reason: "exchange incident", triggered_by: "admin", triggered_at: "2026-10-28T08:00:00Z", resolved_by: null, resolved_at: null, trace_id: "t" };
const recon = {
  id: "recon-12345678", user_id: "u-owner", account_id: "acct-1", mandate_id: "m1", status: "discrepancy", trace_id: "t",
  exchange_balance: { cash: "790" }, ledger_balance: { cash: "0.00000000" }, nav: { cash: "800" },
  differences: [{ source: "exchange_vs_ledger", exchange: "790", ledger: "0.00000000", delta: "790" }],
  actions: ["mandate_paused", "new_orders_forbidden"], created_at: "2026-10-28T00:00:00Z", reviewed: null,
};

async function mockAdmin(page: Page, options: { role?: string; killSwitches?: unknown; refuse?: boolean; readFails?: boolean } = {}) {
  const calls: Call[] = [];
  const role = options.role ?? "admin";
  await page.route("**/me", (route) => route.fulfill({ json: { user: { id: "admin-1", email: "ops@puregamma.ai", name: "Ops", role, plan: "Max", credit_balance: 0, auth_provider: "mock" } } }));
  await page.route("**/__dev-api/admin/trading/**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.postData() ? JSON.parse(request.postData() as string) : null;
    calls.push({ method: request.method(), path: url.pathname.replace("/__dev-api", ""), body });
    if (options.refuse) return route.fulfill({ status: 403, json: { detail: "Admin role required" } });
    if (options.readFails && request.method() === "GET") return route.fulfill({ status: 503, json: { detail: "unavailable" } });
    if (url.pathname.endsWith("/kill-switches")) return route.fulfill({ json: options.killSwitches ?? { active: [active], released: [] } });
    if (url.pathname.endsWith("/kill-switch")) return route.fulfill({ json: { trace_id: "t2", active: body.active, scope: body.scope } });
    if (url.pathname.endsWith("/live-approvals") && request.method() === "GET") return route.fulfill({ json: { approvals: [] } });
    if (url.pathname.endsWith("/live-approvals")) return route.fulfill({ json: { approval: { id: "a1", user_id: body.user_id, email: "trader@example.com", status: body.approve ? "approved" : "rejected", max_total_notional: "1000.00000000", reviewed_by: "admin-1", reviewed_at: "2026-10-29T00:00:00Z", revoked_at: null, notes: body.notes } } });
    if (url.pathname.endsWith("/review")) return route.fulfill({ json: { reconciliation: { ...recon, reviewed: { status: "REVIEWED", reviewed_at: "2026-10-29T00:00:00Z", note: body.note, reviewed_by: "admin-1" } } } });
    if (url.pathname.endsWith("/reconciliations")) return route.fulfill({ json: { reconciliations: [recon] } });
    if (url.pathname.endsWith("/audit")) return route.fulfill({ json: { events: [] } });
    return route.fulfill({ status: 404, json: { detail: "not stubbed" } });
  });
  return calls;
}

const writes = (calls: Call[]) => calls.filter((call) => call.method !== "GET");

test.describe("Admin LIVE review", () => {
  test("a non-administrator sees the access notice and no admin call is made", async ({ page }) => {
    const calls = await mockAdmin(page, { role: "user" });
    await page.goto("/en/admin/trading");
    await expect(page.getByText("Administrator access required")).toBeVisible();
    expect(calls).toEqual([]);
  });

  test("a server refusal is shown as a refusal, not as an empty list", async ({ page }) => {
    await mockAdmin(page, { refuse: true });
    await page.goto("/en/admin/trading");
    await expect(page.getByTestId("admin-kill-switches").getByTestId("admin-live-unavailable")).toContainText("administrator role required");
    await expect(page.getByTestId("admin-kill-none")).toHaveCount(0);
  });

  test("engaging a kill switch needs a reason and the typed phrase, and sends what it stated", async ({ page }) => {
    const calls = await mockAdmin(page, { killSwitches: { active: [], released: [] } });
    await page.goto("/en/admin/trading");
    const section = page.getByTestId("admin-kill-switches");
    await expect(section.getByTestId("admin-kill-none")).toBeVisible();
    const engage = section.getByRole("button", { name: "Engage…" });
    await expect(engage).toBeDisabled();
    await section.getByLabel("Scope").selectOption("user");
    await section.getByLabel("Target id").fill("u-42");
    await section.getByLabel("Reason (required, audited)").fill("suspicious activity");
    await engage.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("user u-42");
    await expect(dialog).toContainText("cancels, queries, fill recording and reconciliation are unaffected");
    const confirm = dialog.getByRole("button", { name: "Confirm" });
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Type the following to confirm").fill("ENGAGE global");
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Type the following to confirm").fill("ENGAGE user");
    await confirm.click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(writes(calls)).toEqual([{ method: "POST", path: "/admin/trading/kill-switch", body: { scope: "user", scope_id: "u-42", active: true, reason: "suspicious activity" } }]);
  });

  test("releasing needs its own reason and states that mandates stay paused", async ({ page }) => {
    const calls = await mockAdmin(page);
    await page.goto("/en/admin/trading");
    const row = page.getByTestId("admin-kill-active");
    await expect(row).toContainText("exchange incident");
    await expect(row.getByRole("button", { name: "Release…" })).toBeDisabled();
    await row.getByLabel("Release reason (required)").fill("venue recovered");
    await row.getByRole("button", { name: "Release…" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("paused mandates are not resumed");
    await dialog.getByLabel("Type the following to confirm").fill("RELEASE global");
    await dialog.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("status").filter({ hasText: "stay paused" })).toBeVisible();
    expect(writes(calls)).toEqual([{ method: "POST", path: "/admin/trading/kill-switch", body: { scope: "global", scope_id: null, active: false, reason: "venue recovered" } }]);
  });

  test("an eligibility decision needs a reason, a decimal cap and the typed phrase", async ({ page }) => {
    const calls = await mockAdmin(page);
    await page.goto("/en/admin/trading");
    const section = page.getByTestId("admin-live-approvals");
    await expect(section.getByTestId("admin-approvals-empty")).toBeVisible();
    await section.getByLabel("User id").fill("u-trader");
    await section.getByLabel("Notional cap (decimal)").fill("1e3");
    await section.getByLabel("Reason (required, audited)").fill("KYC verified");
    await expect(section.getByRole("button", { name: "Submit…" })).toBeDisabled();
    await section.getByLabel("Notional cap (decimal)").fill("1000");
    await section.getByRole("button", { name: "Submit…" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Type the following to confirm").fill("APPROVE u-trader");
    await dialog.getByRole("button", { name: "Confirm" }).click();
    await expect(section.getByRole("status")).toContainText("trader@example.com → approved");
    expect(writes(calls)).toEqual([{ method: "POST", path: "/admin/trading/live-approvals", body: { user_id: "u-trader", approve: true, max_total_notional: "1000", notes: "KYC verified" } }]);
  });

  test("a reconciliation exception shows its differences read-only and is marked reviewed with a note", async ({ page }) => {
    const calls = await mockAdmin(page);
    await page.goto("/en/admin/trading");
    const row = page.getByTestId("admin-recon-row");
    await expect(row.getByTestId("admin-recon-differences")).toContainText("exchange_vs_ledger Δ 790");
    await expect(row).toContainText("mandate_paused");
    await expect(row.locator("input:not([type=checkbox])")).toHaveCount(1);
    await row.getByLabel("Review note (required)").fill("deposit not yet booked");
    await row.getByRole("button", { name: "Mark reviewed…" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Type the following to confirm").fill("REVIEWED recon-12");
    await dialog.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(writes(calls)).toEqual([{ method: "POST", path: "/admin/trading/reconciliations/recon-12345678/review", body: { note: "deposit not yet booked" } }]);
  });

  test("failed reads say so instead of showing empty lists", async ({ page }) => {
    await mockAdmin(page, { readFails: true });
    await page.goto("/en/admin/trading");
    await expect(page.getByTestId("admin-live-unavailable")).toHaveCount(4);
    await expect(page.getByTestId("admin-recon-empty")).toHaveCount(0);
    await expect(page.getByTestId("admin-kill-none")).toHaveCount(0);
  });

  test("fits a phone without horizontal page scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockAdmin(page);
    await page.goto("/en/admin/trading");
    await expect(page.getByTestId("admin-recon-row")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
