import { expect, test, type Page } from "@playwright/test";

/**
 * LIVE trading console smoke tests (frontend-only, API mocked).
 *
 * Covers the delivery contract from docs/live-trading/PROMPT_FRONTEND_LIVE_UI.md:
 * - manifest + safety-status gating (panels registered only when the server
 *   answers and the static gate allows it),
 * - the honest LIVE_DISABLED surface (no trading UI, gate checks listed),
 * - NAV stale → NULL display ("—", never an old number as current),
 * - preview rejection renders the server RiskCheck list and keeps the
 *   confirm action disabled,
 * - the emergency-pause command registration,
 * - screenshots of the two required safety-status states.
 */

const baseManifest = {
  plugins: [
    { id: "puregamma.portfolio", version: "1.0.0", enabled: false, entry: "builtin", required_entitlements: ["portfolio_access"], permissions: ["read:portfolio"], routes: ["/portfolio"] },
    { id: "puregamma.research", version: "1.0.0", enabled: false, entry: "builtin", required_entitlements: ["agent_daily_runs"], permissions: ["read:research"], routes: ["/research", "/reports", "/backtest"] },
    { id: "puregamma.options", version: "1.0.0", enabled: false, entry: "builtin", required_entitlements: [], permissions: ["read:research"], routes: ["/options"] },
    { id: "puregamma.secretary", version: "1.0.0", enabled: false, entry: "builtin", required_entitlements: ["agent_daily_runs"], permissions: ["read:research"], routes: ["/secretary", "/chat"] },
    { id: "puregamma.trading", version: "1.0.0", enabled: false, entry: "builtin", required_entitlements: [], permissions: ["trade:paper"], routes: ["/trading/paper"] },
    { id: "puregamma.live-trading", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: [], permissions: ["read:portfolio", "trade:live"], routes: ["/trading/live", "/trading/live/connect", "/trading/live/orders", "/trading/live/account"] },
  ],
};

const staticChecksDisabled = {
  live_trading_enabled: { ok: false, detail: false },
  deployment_approved: { ok: false, detail: false },
  provider_configured: { ok: false, detail: "" },
  withdrawal_disabled: { ok: true, detail: "" },
  transfer_disabled: { ok: true, detail: "" },
  legacy_runtime_live_off: { ok: true, detail: "" },
  legacy_live_order_off: { ok: true, detail: "" },
};

const staticChecksReady = {
  live_trading_enabled: { ok: true, detail: true },
  deployment_approved: { ok: true, detail: true },
  provider_configured: { ok: true, detail: "binance" },
  withdrawal_disabled: { ok: true, detail: "" },
  transfer_disabled: { ok: true, detail: "" },
  legacy_runtime_live_off: { ok: true, detail: "" },
  legacy_live_order_off: { ok: true, detail: "" },
};

function safetyDisabled() {
  return {
    safety: {
      static_gate: { enabled: false, state: "LIVE_DISABLED", checks: staticChecksDisabled },
      user_live_approval: { status: "none", max_total_notional: "0", reviewed_at: null },
      mandates: {},
      kill_switches: [],
    },
  };
}

function safetyReady() {
  return {
    safety: {
      static_gate: { enabled: true, state: "LIVE_ENABLED", checks: staticChecksReady },
      user_live_approval: { status: "approved", max_total_notional: "5000.00", reviewed_at: "2026-07-20T09:00:00Z" },
      mandates: {
        m1: {
          enabled: true,
          state: "LIVE_ENABLED",
          checks: { mandate_approved: { ok: true, detail: "approval=approved paused=False" } },
        },
      },
      kill_switches: [],
    },
  };
}

function freshNav() {
  return {
    nav: {
      id: "n1",
      account_id: "a1",
      nav: "1234567.89",
      cash: "45000.00",
      gross_exposure: "1234567.89",
      net_exposure: "1234567.89",
      realized_pnl: "12.50",
      unrealized_pnl: "340.00",
      currency: "USD",
      price_timestamp: new Date().toISOString(),
      calculated_at: new Date().toISOString(),
      is_stale: false,
      calculation_version: 2,
      reconciliation_status: "ok",
    },
    daily_pnl: "10.00",
    daily_return: "0.001",
  };
}

function staleNav() {
  return {
    nav: {
      ...freshNav().nav,
      nav: null,
      price_timestamp: null,
      is_stale: true,
    },
    daily_pnl: null,
    daily_return: null,
  };
}

function liveMandate() {
  return {
    mandates: [
      {
        id: "m1",
        account_id: "a1",
        execution_mode: "live",
        environment: "production",
        status: "active",
        allowed_symbols: ["BTC", "ETH"],
        allowed_side: "both",
        max_total_notional: "5000.00",
        max_per_order_notional: "1000.00",
        max_position_notional: "4000.00",
        max_leverage: "1",
        max_daily_loss: "250.00",
        max_trades_per_day: 5,
        max_order_frequency_seconds: 10,
        kill_switch_state: "inactive",
        paused: false,
        pause_reason: null,
        approval_status: "approved",
        approved_by: null,
        approved_at: "2026-07-20T09:00:00Z",
        expires_at: null,
        created_at: "2026-07-20T09:00:00Z",
      },
    ],
  };
}

declare global {
  interface Window {
    __PUREGAMMA_PLUGIN_RUNTIME__?: {
      loadedPlugins: string[];
      panelIds: string[];
      commandIds: string[];
      realtimeConnections: number;
      disposed: boolean;
    };
  }
}

async function mockCommonEndpoints(page: Page, safety: Record<string, unknown>) {
  await page.route("**/api/frontend/plugins", (route) => route.fulfill({ json: baseManifest }));
  await page.route("**/api/trading/safety-status", (route) => route.fulfill({ json: safety }));
  await page.route("**/api/trading/mandates", (route) => route.fulfill({ json: liveMandate() }));
  await page.route("**/api/trading/connections", (route) => route.fulfill({ json: { connections: [] } }));
  await page.route("**/api/trading/orders", (route) => route.fulfill({ json: { orders: [] } }));
  await page.route("**/api/portfolio/positions", (route) => route.fulfill({ json: { positions: [] } }));
  // A signed-in session so the shell does not fire the auth-expired redirect.
  await page.route("**/me", (route) =>
    route.fulfill({
      json: { user: { id: "u1", email: "demo@puregamma.ai", name: "Demo User", role: "user", plan: "Free", credit_balance: 10, auth_provider: "mock" } },
    })
  );
}

const diagnostics = (page: Page) =>
  page.evaluate(() => window.__PUREGAMMA_PLUGIN_RUNTIME__);

test.describe("LIVE trading console", () => {
  test("LIVE_DISABLED renders the honest disabled surface only", async ({ page }) => {
    await mockCommonEndpoints(page, safetyDisabled());
    await page.route("**/api/portfolio/nav", (route) => route.fulfill({ json: freshNav() }));

    await page.goto("/en/trading/live");

    // Honest disabled panel: title, gate checks, blocked rows.
    await expect(page.locator('[data-testid="live-disabled-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="live-disabled-panel"]').getByRole("heading", { name: "LIVE trading is disabled" })).toBeVisible();
    await expect(page.getByText("Static gate checks")).toBeVisible();
    await expect(page.getByText("live_trading_enabled")).toBeVisible();
    await expect(page.getByText("blocked").first()).toBeVisible();
    await expect(page.getByText("Apply for LIVE access")).toBeVisible();

    // No trading UI at all while disabled.
    await expect(page.locator('[data-testid="live-order-form"]')).toHaveCount(0);

    // Plugin gating: only the overview panel registers, no emergency command.
    await expect
      .poll(async () => (await diagnostics(page))?.panelIds ?? [])
      .toContain("live.overview");
    const panels = (await diagnostics(page))?.panelIds ?? [];
    expect(panels).not.toContain("live.orders");
    const commands = (await diagnostics(page))?.commandIds ?? [];
    expect(commands).not.toContain("live.emergency-pause");

    await page.screenshot({ path: test.info().outputPath("live-disabled.png"), fullPage: true });
  });

  test("READY state registers all panels + command and shows a fresh NAV", async ({ page }) => {
    await mockCommonEndpoints(page, safetyReady());
    await page.route("**/api/portfolio/nav", (route) => route.fulfill({ json: freshNav() }));

    await page.goto("/en/trading/live");

    await expect(page.locator('[data-testid="live-disabled-panel"]')).toHaveCount(0);
    await expect(page.getByText("LIVE", { exact: true }).first()).toBeVisible();
    // Decimal string rendered verbatim with grouping; no float math.
    await expect(page.locator('[data-testid="live-nav-value"]')).toHaveText("1,234,567.89 USD");

    await expect
      .poll(async () => (await diagnostics(page))?.panelIds ?? [])
      .toContain("live.orders");
    const panels = (await diagnostics(page))?.panelIds ?? [];
    for (const id of ["live.overview", "live.connect", "live.orders", "live.account"]) {
      expect(panels).toContain(id);
    }
    const commands = (await diagnostics(page))?.commandIds ?? [];
    expect(commands).toContain("live.emergency-pause");

    await page.screenshot({ path: test.info().outputPath("live-ready.png"), fullPage: true });
  });

  test("stale NAV renders NULL semantics (—) instead of an old number", async ({ page }) => {
    await mockCommonEndpoints(page, safetyReady());
    await page.route("**/api/portfolio/nav", (route) => route.fulfill({ json: staleNav() }));

    await page.goto("/en/trading/live");

    await expect(page.locator('[data-testid="live-nav-value"]')).toHaveText("—");
    await expect(page.getByText(/stale or missing/i)).toBeVisible();
  });

  test("safety-status 501 → no panels, disabled nav item, unavailable panel", async ({ page }) => {
    await mockCommonEndpoints(page, safetyReady());
    await page.route("**/api/trading/safety-status", (route) =>
      route.fulfill({ status: 501, json: { detail: "not implemented" } })
    );

    await page.goto("/en/trading/live");

    await expect(page.locator('[data-testid="live-unavailable-panel"]')).toBeVisible();
    await expect(page.getByText("LIVE trading console unavailable")).toBeVisible();
    // Disabled nav placeholder (sidebar + mobile drawer both render it).
    await expect(page.getByText("LIVE Trading (not enabled)").first()).toBeVisible();

    const panels = (await diagnostics(page))?.panelIds ?? [];
    expect(panels.filter((id) => id.startsWith("live."))).toEqual([]);
    const commands = (await diagnostics(page))?.commandIds ?? [];
    expect(commands).not.toContain("live.emergency-pause");
  });

  test("order preview rejection renders the server risk checks and disables confirm", async ({ page }) => {
    await mockCommonEndpoints(page, safetyReady());
    await page.route("**/api/trading/orders/preview", (route) =>
      route.fulfill({
        status: 400,
        json: {
          detail: {
            code: "ORDER_REJECTED",
            message: "LIVE disabled: broker_connection_healthy,user_live_approved",
            checks: [
              { check: "asset_whitelist", ok: false, detail: "DOGE not in mandate/config whitelist" },
              { check: "balance_check", ok: true, detail: "available=1000.00" },
              { check: "kill_switch", ok: true, detail: "clear" },
            ],
          },
        },
      })
    );

    await page.goto("/en/trading/live/orders");

    const form = page.locator('[data-testid="live-order-form"]');
    await expect(form).toBeVisible();
    await form.getByLabel("Symbol").fill("DOGE");
    await form.getByLabel("Quantity").fill("0.5");
    await form.getByRole("button", { name: "Preview order" }).click();

    await expect(page.locator('[data-testid="live-preview-rejection"]')).toBeVisible();
    await expect(page.getByText("Order rejected by the risk engine")).toBeVisible();
    await expect(page.getByText("asset_whitelist")).toBeVisible();
    await expect(page.getByText("REJECTED").first()).toBeVisible();
    // No intent card → no confirm entry point at all.
    await expect(page.getByText("Order intent (pending confirmation)")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Submit order" })).toHaveCount(0);
  });
});
