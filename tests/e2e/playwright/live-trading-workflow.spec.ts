import { expect, test, type Page, type Request } from "@playwright/test";

/**
 * LIVE order workflow (frontend only; every endpoint is stubbed).
 *
 * What these pin is the money-safety behaviour of the console, not its looks:
 * - the approval card names action, scope, impact, authority and expiry, and
 *   an expired preview cannot be approved;
 * - a confirm with no definite answer becomes "result unknown": the console
 *   reconciles against the order list, blocks a fresh preview, and the only
 *   retry it offers re-sends the SAME intent and phrase;
 * - a definite 4xx is shown as "not submitted" with the server's reason;
 * - an UNKNOWN order is explained and never re-submitted by the page;
 * - "no LIVE account" is not rendered as a zero NAV.
 */

const manifest = {
  plugins: [
    { id: "puregamma.live-trading", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: [], permissions: ["read:portfolio", "trade:live"], routes: ["/trading/live", "/trading/live/connect", "/trading/live/orders", "/trading/live/account"] },
  ],
};

const readyChecks = {
  live_trading_enabled: { ok: true, detail: true },
  deployment_approved: { ok: true, detail: true },
  provider_configured: { ok: true, detail: "binance_spot" },
  withdrawal_disabled: { ok: true, detail: "" },
  transfer_disabled: { ok: true, detail: "" },
};

const safety = {
  safety: {
    static_gate: { enabled: true, state: "LIVE_ENABLED", checks: readyChecks },
    user_live_approval: { status: "approved", max_total_notional: "50000.00", reviewed_at: "2026-10-20T09:00:00Z" },
    mandates: { m1: { enabled: true, state: "LIVE_ENABLED", checks: { mandate_approved: { ok: true, detail: "approval=approved paused=False" } } } },
    kill_switches: [],
  },
};

const mandate = {
  id: "m1aaaaaaaa", account_id: "a1", execution_mode: "live", environment: "production", status: "active",
  allowed_symbols: ["BTCUSDT", "ETHUSDT"], allowed_side: "both",
  max_total_notional: "50000.00", max_per_order_notional: "40000.00", max_position_notional: "45000.00",
  max_leverage: "1", max_daily_loss: "500.00", max_trades_per_day: 10, max_order_frequency_seconds: 5,
  kill_switch_state: "inactive", paused: false, pause_reason: null, approval_status: "approved",
  approved_by: null, approved_at: "2026-10-20T09:00:00Z", expires_at: null, created_at: "2026-10-20T09:00:00Z",
};

function preview(expiresInSeconds = 600) {
  return {
    intent: {
      id: "intent-123456789", mandate_id: mandate.id, symbol: "BTCUSDT", side: "buy", quantity: "0.5",
      order_type: "limit", limit_price: "64000.10", source: "user_confirmed", status: "pending",
      requested_at: new Date().toISOString(), expires_at: new Date(Date.now() + expiresInSeconds * 1000).toISOString(), confirmation_required: true,
    },
    confirmation: "CONFIRM LIVE BTCUSDT BUY 0.5 k3y9",
    trace_id: "trace-abc",
  };
}

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: "o1", mandate_id: mandate.id, order_intent_id: "intent-123456789", symbol: "BTCUSDT", side: "buy", quantity: "0.50000000",
    order_type: "limit", limit_price: "64000.10000000", status: "accepted", client_order_id: "pg-0123456789abcdef0123",
    broker_order_id: "b-1", filled_quantity: "0.00000000", average_price: null, submitted_at: new Date().toISOString(),
    last_sync_at: new Date().toISOString(), error_code: null, error_message: null, created_at: new Date().toISOString(), trace_id: "trace-abc",
    ...overrides,
  };
}

type Mocks = { orders?: () => unknown[]; confirm?: (request: Request) => { status: number; json: unknown }; nav?: { status: number; json: unknown } };

async function mockLive(page: Page, mocks: Mocks = {}) {
  await page.route("**/api/frontend/plugins", (route) => route.fulfill({ json: manifest }));
  await page.route("**/me", (route) => route.fulfill({ json: { user: { id: "u1", email: "demo@puregamma.ai", name: "Demo", role: "user", plan: "Max", credit_balance: 10, auth_provider: "mock" } } }));
  await page.route("**/api/trading/safety-status", (route) => route.fulfill({ json: safety }));
  await page.route("**/api/trading/mandates", (route) => route.fulfill({ json: { mandates: [mandate] } }));
  await page.route("**/api/trading/connections", (route) => route.fulfill({ json: { connections: [{ id: "c1", provider: "binance_spot", account_label: "Main", environment: "production", status: "HEALTHY", permissions: null, has_credentials: true, last_health_check_at: null, revoked_at: null, created_at: "2026-10-20T09:00:00Z" }] } }));
  await page.route("**/api/trading/orders", (route) => route.fulfill({ json: { orders: mocks.orders ? mocks.orders() : [] } }));
  await page.route("**/api/trading/fills**", (route) => route.fulfill({ json: { fills: [{ id: "f1", order_id: "o1", symbol: "BTCUSDT", side: "buy", quantity: "0.25000000", price: "64000.10000000", fee: "0.00025000", fee_currency: "BTC", executed_at: "2026-10-28T08:00:00Z", broker_fill_id: "bf1" }] } }));
  await page.route("**/api/trading/orders/preview", (route) => route.fulfill({ json: preview() }));
  await page.route("**/api/trading/orders/confirm", (route) => {
    const answer = mocks.confirm ? mocks.confirm(route.request()) : { status: 200, json: { order: order() } };
    return route.fulfill({ status: answer.status, json: answer.json });
  });
  await page.route("**/api/portfolio/positions", (route) => route.fulfill({ json: { positions: [] } }));
  await page.route("**/api/portfolio/nav", (route) => route.fulfill(mocks.nav ?? { status: 404, json: { detail: { code: "TRADING_ACCOUNT_NOT_FOUND", message: "No active trading account" } } }));
}

async function previewLimitOrder(page: Page) {
  const form = page.locator('[data-testid="live-order-form"]');
  await expect(form.getByLabel("Symbol")).toHaveValue("BTCUSDT");
  await form.getByLabel("Order type").selectOption("limit");
  await form.getByLabel("Quantity").fill("0.5");
  await form.getByLabel("Limit price").fill("64000.10");
  await form.getByRole("button", { name: "Preview order" }).click();
  await expect(page.locator('[data-testid="live-order-approval"]')).toBeVisible();
}

async function approve(page: Page) {
  const card = page.locator('[data-testid="live-order-approval"]');
  await card.getByLabel(/confirmation/i).fill("CONFIRM LIVE BTCUSDT BUY 0.5 k3y9");
  await card.getByRole("button", { name: "Approve and submit" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /submit|confirm/i }).last().click();
}

test.describe("LIVE order workflow", () => {
  test("the approval card states action, scope, exact impact, authority and validity", async ({ page }) => {
    await mockLive(page);
    await page.goto("/en/trading/live/orders");
    await previewLimitOrder(page);

    const card = page.locator('[data-testid="live-order-approval"]');
    await expect(card.getByTestId("approval-action")).toHaveText("BUY 0.5 BTCUSDT · limit @ 64,000.10");
    await expect(card).toContainText("Mandate m1aaaaaa");
    // 0.5 × 64000.10 computed exactly (no binary float): 32,000.05.
    await expect(card).toContainText("32,000.05");
    await expect(card).toContainText("approved");
    await expect(card).toContainText("50,000.00");
    await expect(card.getByTestId("approval-validity")).toContainText(/s left/);
    await expect(card.getByRole("button", { name: "Approve and submit" })).toBeDisabled();

    // Reject = discard locally; nothing is sent.
    let confirms = 0;
    page.on("request", (request) => { if (request.url().includes("/orders/confirm")) confirms += 1; });
    await card.getByRole("button", { name: "Reject this intent" }).click();
    await expect(card).toHaveCount(0);
    await expect(page.getByText(/Nothing was submitted/)).toBeVisible();
    expect(confirms).toBe(0);
  });

  test("an expired preview cannot be approved", async ({ page }) => {
    await mockLive(page);
    await page.route("**/api/trading/orders/preview", (route) => route.fulfill({ json: preview(-5) }));
    await page.goto("/en/trading/live/orders");
    await previewLimitOrder(page);
    const card = page.locator('[data-testid="live-order-approval"]');
    await expect(card.getByTestId("approval-validity")).toContainText(/expired/i);
    await expect(card.getByLabel(/confirmation/i)).toBeDisabled();
    await expect(card.getByRole("button", { name: "Approve and submit" })).toBeDisabled();
  });

  test("a confirm without a definite answer reconciles and only re-sends the same intent", async ({ page }) => {
    let accepted = false;
    const bodies: Array<{ order_intent_id: string; confirmation: string }> = [];
    let previews = 0;
    await mockLive(page, {
      orders: () => (accepted ? [order()] : []),
      confirm: (request) => {
        bodies.push(request.postDataJSON());
        if (bodies.length === 1) return { status: 502, json: { detail: "Bad gateway" } };
        accepted = true;
        return { status: 200, json: { order: order() } };
      },
    });
    page.on("request", (request) => { if (request.url().includes("/orders/preview")) previews += 1; });
    await page.goto("/en/trading/live/orders");
    await previewLimitOrder(page);
    await approve(page);

    const panel = page.locator('[data-testid="live-submission-ambiguous"]');
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Submission result unknown");
    await expect(panel).toContainText("No order for this intent is visible yet.");
    // A new preview for the same trade is blocked until this is resolved.
    await expect(page.getByRole("button", { name: "Preview order" })).toBeDisabled();

    await panel.getByRole("button", { name: "Re-send the same intent" }).click();
    await expect(panel).toHaveCount(0);
    await expect(page.getByText("pg-0123456789abcdef0123")).toBeVisible();

    expect(previews).toBe(1);
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual(bodies[0]);
    expect(bodies[0]).toEqual({ order_intent_id: "intent-123456789", confirmation: "CONFIRM LIVE BTCUSDT BUY 0.5 k3y9" });
  });

  test("when the order already exists, reconciliation finds it and nothing is re-sent", async ({ page }) => {
    let confirmCalls = 0;
    let listed = false;
    await mockLive(page, {
      orders: () => (listed ? [order({ status: "unknown", error_code: "SUBMIT_UNKNOWN" })] : []),
      confirm: () => {
        confirmCalls += 1;
        listed = true; // the server stored the order even though the response was lost
        return { status: 504, json: { detail: "Gateway timeout" } };
      },
    });
    await page.goto("/en/trading/live/orders");
    await previewLimitOrder(page);
    await approve(page);
    await expect(page.locator('[data-testid="live-submission-ambiguous"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="live-unknown-banner"]')).toContainText("never retried automatically");
    await expect(page.locator('[data-testid="live-order-unknown"]')).toBeVisible();
    await expect(page.getByText(/reconciling, never retried/).first()).toBeVisible();
    expect(confirmCalls).toBe(1);
  });

  test("a definite rejection says the order was not submitted, with the server reason", async ({ page }) => {
    await mockLive(page, { confirm: () => ({ status: 400, json: { detail: "Order confirmation expired" } }) });
    await page.goto("/en/trading/live/orders");
    await previewLimitOrder(page);
    await approve(page);
    const rejected = page.locator('[data-testid="live-submission-rejected"]');
    await expect(rejected).toContainText("Not submitted");
    await expect(rejected).toContainText("Order confirmation expired");
    await expect(page.locator('[data-testid="live-order-approval"]')).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Preview order" })).toBeEnabled();
  });

  test("a preview outage is not reported as a risk rejection", async ({ page }) => {
    await mockLive(page);
    await page.route("**/api/trading/orders/preview", (route) => route.fulfill({ status: 503, json: { detail: "upstream down" } }));
    await page.goto("/en/trading/live/orders");
    const form = page.locator('[data-testid="live-order-form"]');
    await form.getByLabel("Quantity").fill("0.5");
    await form.getByRole("button", { name: "Preview order" }).click();
    await expect(page.getByText("The order preview service is unavailable; no intent was created.")).toBeVisible();
    await expect(page.locator('[data-testid="live-preview-rejection"]')).toHaveCount(0);
  });

  test("fills are listed from the server", async ({ page }) => {
    await mockLive(page, { orders: () => [order({ status: "partially_filled", filled_quantity: "0.25000000" })] });
    await page.goto("/en/trading/live/orders");
    const fills = page.locator('[data-testid="live-fills"]');
    await expect(fills).toContainText("64,000.1");
    await expect(fills).toContainText("0.00025000 BTC");
    await expect(page.getByText("Refreshing every 10 s while orders are open")).toBeVisible();
  });

  test("no LIVE account is shown as unavailable, never as a zero NAV", async ({ page }) => {
    await mockLive(page);
    await page.goto("/en/trading/live");
    await expect(page.locator('[data-testid="live-nav-no-account"]')).toContainText("it is not zero");
    await expect(page.locator('[data-testid="live-nav-value"]')).toHaveCount(0);
  });

  test("revoking a connection uses a keyboard-safe dialog and states what it does", async ({ page }) => {
    let revoked = 0;
    await mockLive(page);
    await page.route("**/api/trading/connections/c1/revoke", (route) => { revoked += 1; return route.fulfill({ json: { connection: {} } }); });
    await page.goto("/en/trading/live/connect");
    const trigger = page.getByRole("button", { name: "Revoke" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Revoke this connection?" });
    await expect(dialog).toContainText("Open orders are not canceled");
    // The safe action has focus first; Escape closes and returns focus.
    await expect(dialog.getByRole("button", { name: "Back" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    expect(revoked).toBe(0);

    await trigger.click();
    await page.getByRole("dialog").getByRole("button", { name: "Revoke" }).click();
    await expect(page.getByText("Connection revoked; bound mandates paused.")).toBeVisible();
    expect(revoked).toBe(1);
  });

  test("orders view fits a phone without horizontal page scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockLive(page, { orders: () => [order({ status: "unknown" })] });
    await page.goto("/en/trading/live/orders");
    await expect(page.locator('[data-testid="live-unknown-banner"]')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: test.info().outputPath("live-orders-mobile.png"), fullPage: true });
  });
});
