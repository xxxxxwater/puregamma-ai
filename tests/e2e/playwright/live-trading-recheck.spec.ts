import { expect, test, type Page, type Request } from "@playwright/test";

/**
 * UNKNOWN orders: sync status and the query-only re-check (frontend only;
 * every endpoint is stubbed).
 *
 * - the panel states when the venue was last asked and what it answered;
 * - "ask again" posts only to /recheck — never to preview/confirm/cancel;
 * - a 429 is explained; a disabled deployment offers no button.
 */

const manifest = {
  plugins: [
    { id: "puregamma.live-trading", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: [], permissions: ["read:portfolio", "trade:live"], routes: ["/trading/live", "/trading/live/connect", "/trading/live/orders", "/trading/live/account"] },
  ],
};

const safety = {
  safety: {
    static_gate: { enabled: true, state: "LIVE_ENABLED", checks: { live_trading_enabled: { ok: true, detail: true } } },
    user_live_approval: { status: "approved", max_total_notional: "50000.00", reviewed_at: "2026-10-20T09:00:00Z" },
    mandates: {},
    kill_switches: [],
  },
};

const unknownOrder = {
  id: "o-unknown", mandate_id: "m1", order_intent_id: "i1", symbol: "BTCUSDT", side: "buy", quantity: "0.50000000",
  order_type: "market", limit_price: null, status: "unknown", client_order_id: "pg-unknown000000000001",
  broker_order_id: null, filled_quantity: "0.00000000", average_price: null, submitted_at: "2026-10-28T08:00:00Z",
  last_sync_at: "2026-10-28T08:05:00Z", error_code: "SUBMIT_UNKNOWN", error_message: "timeout", created_at: "2026-10-28T08:00:00Z", trace_id: "t",
};

function syncStatus(overrides: Record<string, unknown> = {}, recheck: Record<string, unknown> = {}) {
  return {
    sync: {
      order_id: unknownOrder.id, status: "unknown", error_code: "SUBMIT_UNKNOWN", last_sync_at: "2026-10-28T08:05:00Z",
      latest: { at: "2026-10-28T08:05:00Z", trigger: "background", outcome: "query_failed", state_before: "unknown", state_after: "unknown", reason: "venue timeout after 8s" },
      history: [],
      recheck: { enabled: true, allowed: true, blocked_reason: null, min_interval_seconds: 60, next_allowed_at: null, ...recheck },
      ...overrides,
    },
  };
}

async function mockLive(page: Page, handlers: { status?: () => unknown; recheck?: () => { status: number; json: unknown } }) {
  const writes: string[] = [];
  page.on("request", (request: Request) => {
    if (request.method() !== "GET" && request.url().includes("/api/trading/")) writes.push(new URL(request.url()).pathname);
  });
  await page.route("**/api/frontend/plugins", (route) => route.fulfill({ json: manifest }));
  await page.route("**/me", (route) => route.fulfill({ json: { user: { id: "u1", email: "demo@puregamma.ai", name: "Demo", role: "user", plan: "Max", credit_balance: 10, auth_provider: "mock" } } }));
  await page.route("**/api/trading/safety-status", (route) => route.fulfill({ json: safety }));
  await page.route("**/api/trading/mandates", (route) => route.fulfill({ json: { mandates: [] } }));
  await page.route("**/api/trading/orders", (route) => route.fulfill({ json: { orders: [unknownOrder] } }));
  await page.route("**/api/trading/fills**", (route) => route.fulfill({ json: { fills: [] } }));
  await page.route("**/api/trading/orders/*/sync-status", (route) => route.fulfill({ json: handlers.status ? handlers.status() : syncStatus() }));
  await page.route("**/api/trading/orders/*/recheck", (route) => {
    const answer = handlers.recheck ? handlers.recheck() : { status: 200, json: syncStatus() };
    return route.fulfill({ status: answer.status, json: answer.json });
  });
  await page.route("**/api/portfolio/**", (route) => route.fulfill({ status: 404, json: { detail: { code: "TRADING_ACCOUNT_NOT_FOUND", message: "none" } } }));
  return writes;
}

test.describe("LIVE UNKNOWN order sync", () => {
  test("states the last query and its answer, and asking again only posts /recheck", async ({ page }) => {
    const writes = await mockLive(page, {
      recheck: () => ({ status: 200, json: syncStatus({ latest: { at: "2026-10-28T08:06:00Z", trigger: "user_recheck", outcome: "still_unknown", state_before: "unknown", state_after: "unknown", reason: "not visible yet" } }, { allowed: false, blocked_reason: "rate_limited", next_allowed_at: "2026-10-28T08:07:00Z" }) }),
    });
    await page.goto("/en/trading/live/orders");
    const panel = page.getByTestId("live-order-sync");
    await expect(panel.getByTestId("live-order-sync-latest")).toContainText("The query failed");
    await expect(panel.getByTestId("live-order-sync-latest")).toContainText("venue timeout after 8s");
    await expect(panel).toContainText("never places, re-sends or changes an order");

    await panel.getByTestId("live-order-recheck").click();
    await expect(panel.getByTestId("live-order-sync-latest")).toContainText("Still unknown at the venue");
    await expect(panel.getByTestId("live-order-sync-latest")).toContainText("not visible yet");
    await expect(panel.getByTestId("live-order-recheck")).toBeDisabled();
    await expect(panel).toContainText("Can ask again after");
    expect(writes).toEqual(["/__dev-api/api/trading/orders/o-unknown/recheck"]);
  });

  test("a rate-limited request is explained and nothing else is sent", async ({ page }) => {
    const writes = await mockLive(page, {
      recheck: () => ({ status: 429, json: { detail: { code: "LIVE_ORDER_RECHECK_RATE_LIMITED", message: "Re-check allowed again in 42s", retry_after_seconds: 42 } } }),
    });
    await page.goto("/en/trading/live/orders");
    const panel = page.getByTestId("live-order-sync");
    await panel.getByTestId("live-order-recheck").click();
    await expect(panel.getByRole("status")).toContainText("Asked too recently");
    expect(writes).toEqual(["/__dev-api/api/trading/orders/o-unknown/recheck"]);
  });

  test("a deployment without on-demand re-check offers no button", async ({ page }) => {
    await mockLive(page, { status: () => syncStatus({}, { enabled: false, allowed: false, blocked_reason: "disabled" }) });
    await page.goto("/en/trading/live/orders");
    const panel = page.getByTestId("live-order-sync");
    await expect(panel).toContainText("not enabled on this deployment");
    await expect(panel.getByTestId("live-order-recheck")).toHaveCount(0);
  });

  test("a cancel the venue did not confirm is not reported as cancelled", async ({ page }) => {
    const open = { ...unknownOrder, id: "o-open", status: "accepted", client_order_id: "pg-open00000000000000001", error_code: null, error_message: null };
    await mockLive(page, {});
    await page.route("**/api/trading/orders", (route) => route.fulfill({ json: { orders: [open] } }));
    const cancels: unknown[] = [];
    await page.route("**/api/trading/orders/cancel", (route) => {
      cancels.push(JSON.parse(route.request().postData() || "{}"));
      return route.fulfill({ json: { order: { ...open, error_code: "CANCEL_UNKNOWN", error_message: "venue timeout" } } });
    });
    await page.goto("/en/trading/live/orders");
    await page.getByRole("button", { name: "Cancel order" }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel order" }).click();
    await expect(page.getByText("The venue did not confirm the cancel")).toBeVisible();
    await expect(page.getByText("Cancel requested.")).toHaveCount(0);
    expect(cancels).toEqual([{ client_order_id: "pg-open00000000000000001" }]);
  });

  test("an unreadable sync history says so instead of guessing", async ({ page }) => {
    await mockLive(page, {});
    await page.route("**/api/trading/orders/*/sync-status", (route) => route.fulfill({ status: 503, json: { detail: "unavailable" } }));
    await page.goto("/en/trading/live/orders");
    await expect(page.getByTestId("live-order-sync-unavailable")).toBeVisible();
    await expect(page.getByTestId("live-order-unknown")).toBeVisible();
  });
});
