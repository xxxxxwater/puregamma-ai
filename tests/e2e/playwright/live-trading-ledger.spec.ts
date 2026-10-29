import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * LIVE account: the user's own ledger and reconciliation (frontend only; every
 * endpoint is stubbed).
 *
 * What these pin:
 * - ledger rows show the server's decimal strings verbatim, and a missing
 *   running balance reads "not recorded", not 0;
 * - older rows are fetched with the server's opaque cursor and appended; a
 *   failed page keeps what is shown;
 * - "no account", "could not be read" and "no rows yet" are three different
 *   messages, none of them a zero;
 * - "never reconciled" is not presented as "no differences".
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

const account = { id: "acct-1", name: "Main", venue: "BINANCE", account_type: "LIVE", base_currency: "USD", status: "ACTIVE" };

function entry(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `led-${index}`, account_id: account.id, mandate_id: "m1", entry_type: "trade_buy", ref_type: "fill", ref_id: `fill-${index}`,
    symbol: "BTCUSDT", quantity: "0.00100000", price: "64000.10000000", amount: "-64.00010000", currency: "USD",
    balance_after: "936.00000000", trace_id: "t", created_at: `2026-10-28T08:${String(59 - index).padStart(2, "0")}:00Z`,
    ...overrides,
  };
}

const notFound = { status: 404, json: { detail: { code: "TRADING_ACCOUNT_NOT_FOUND", message: "Trading account not found" } } };

type Answer = { status?: number; json: unknown };
type Mocks = { ledger?: (route: Route, url: URL) => Answer; reconciliation?: () => Answer };

async function mockLive(page: Page, mocks: Mocks) {
  await page.route("**/api/frontend/plugins", (route) => route.fulfill({ json: manifest }));
  await page.route("**/me", (route) => route.fulfill({ json: { user: { id: "u1", email: "demo@puregamma.ai", name: "Demo", role: "user", plan: "Max", credit_balance: 10, auth_provider: "mock" } } }));
  await page.route("**/api/trading/safety-status", (route) => route.fulfill({ json: safety }));
  await page.route("**/api/trading/mandates", (route) => route.fulfill({ json: { mandates: [] } }));
  await page.route("**/api/portfolio/positions", (route) => route.fulfill({ json: { positions: [] } }));
  await page.route("**/api/portfolio/nav", (route) => route.fulfill(notFound));
  await page.route("**/api/trading/ledger**", (route) => {
    const answer = mocks.ledger ? mocks.ledger(route, new URL(route.request().url())) : notFound;
    return route.fulfill({ status: answer.status ?? 200, json: answer.json });
  });
  await page.route("**/api/trading/reconciliation**", (route) => {
    const answer = mocks.reconciliation ? mocks.reconciliation() : notFound;
    return route.fulfill({ status: answer.status ?? 200, json: answer.json });
  });
}

const emptyLedgerSummary = { entry_count: 0, empty: true, last_entry_at: null, balances: [], positions: [] };

test.describe("LIVE account ledger and reconciliation", () => {
  test("rows are server decimal strings; older pages use the cursor and append", async ({ page }) => {
    const cursors: Array<string | null> = [];
    await mockLive(page, {
      ledger: (_route, url) => {
        const cursor = url.searchParams.get("cursor");
        cursors.push(cursor);
        if (!cursor) return { json: { account, entries: [entry(0), entry(1, { entry_type: "cash_deposit", symbol: null, quantity: null, price: null, amount: "1000.00000000", balance_after: null, ref_type: "deposit" })], next_cursor: "opaque-cursor-1", limit: 50 } };
        return { json: { account, entries: [entry(2, { entry_type: "fee", amount: "-0.00000001", currency: "BTC", symbol: null, quantity: null, price: null })], next_cursor: null, limit: 50 } };
      },
      reconciliation: () => ({ json: { account, ledger: { entry_count: 3, empty: false, last_entry_at: "2026-10-28T08:59:00Z", balances: [{ currency: "BTC", amount: "-0.00000001" }, { currency: "USD", amount: "936.00000000" }], positions: [] }, latest: null, history: [] } }),
    });
    await page.goto("/en/trading/live/account");

    const ledger = page.getByTestId("live-ledger");
    await expect(ledger.getByTestId("live-ledger-row")).toHaveCount(2);
    const first = ledger.getByTestId("live-ledger-row").first();
    await expect(first).toContainText("-64.00010000 USD");
    await expect(first).toContainText("64,000.10000000");
    await expect(first).toContainText("0.00100000");
    // A running balance the server did not record is not a zero.
    await expect(ledger.getByTestId("live-ledger-row").nth(1)).toContainText("not recorded");

    await ledger.getByTestId("live-ledger-more").click();
    await expect(ledger.getByTestId("live-ledger-row")).toHaveCount(3);
    await expect(ledger.getByTestId("live-ledger-row").nth(2)).toContainText("-0.00000001 BTC");
    await expect(ledger.getByTestId("live-ledger-end")).toBeVisible();
    expect(cursors).toEqual([null, "opaque-cursor-1"]);

    // Balances are per currency; never re-added into one number.
    await expect(page.getByTestId("live-recon-balances")).toContainText("936.00000000 USD");
    await expect(page.getByTestId("live-recon-balances")).toContainText("-0.00000001 BTC");
    await expect(page.getByTestId("live-recon-never")).toContainText("never been reconciled");
  });

  test("a failed older page keeps the rows already shown", async ({ page }) => {
    await mockLive(page, {
      ledger: (_route, url) => (url.searchParams.get("cursor") ? { status: 503, json: { detail: "unavailable" } } : { json: { account, entries: [entry(0)], next_cursor: "c1", limit: 50 } }),
      reconciliation: () => ({ json: { account, ledger: emptyLedgerSummary, latest: null, history: [] } }),
    });
    await page.goto("/en/trading/live/account");
    const ledger = page.getByTestId("live-ledger");
    await expect(ledger.getByTestId("live-ledger-row")).toHaveCount(1);
    await ledger.getByTestId("live-ledger-more").click();
    await expect(ledger.getByRole("alert")).toContainText("could not be loaded");
    await expect(ledger.getByTestId("live-ledger-row")).toHaveCount(1);
    await expect(ledger.getByTestId("live-ledger-more")).toBeEnabled();
  });

  test("no LIVE account is unavailable, not a zero balance", async ({ page }) => {
    await mockLive(page, {});
    await page.goto("/en/trading/live/account");
    await expect(page.getByTestId("live-ledger-no-account")).toContainText("it is not zero");
    await expect(page.getByTestId("live-recon-no-account")).toContainText("unavailable");
    await expect(page.getByTestId("live-ledger")).not.toContainText(/\b0\.00\b/);
    await expect(page.getByTestId("live-ledger-row")).toHaveCount(0);
  });

  test("an outage says unavailable with a retry, and the retry reads again", async ({ page }) => {
    let calls = 0;
    await mockLive(page, {
      ledger: () => (++calls === 1 ? { status: 503, json: { detail: "unavailable" } } : { json: { account, entries: [entry(0)], next_cursor: null, limit: 50 } }),
      reconciliation: () => ({ status: 500, json: { detail: "boom" } }),
    });
    await page.goto("/en/trading/live/account");
    const unavailable = page.getByTestId("live-ledger-unavailable");
    await expect(unavailable).toContainText("not an empty ledger");
    await expect(page.getByTestId("live-recon-unavailable")).toContainText("not the same as");
    await unavailable.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("live-ledger-row")).toHaveCount(1);
  });

  test("an empty ledger and a reconciliation with differences are stated as such", async ({ page }) => {
    await mockLive(page, {
      ledger: () => ({ json: { account, entries: [], next_cursor: null, limit: 50 } }),
      reconciliation: () => ({
        json: {
          account,
          ledger: emptyLedgerSummary,
          latest: {
            id: "r1", account_id: account.id, mandate_id: "m1", status: "discrepancy",
            exchange_balance: { cash: "790", equity: null }, ledger_balance: { cash: "0.00000000" }, nav: { cash: "800", nav: null },
            differences: [{ source: "exchange_vs_ledger", exchange: "790", ledger: "0.00000000", delta: "790" }],
            actions: ["mandate_paused"], created_at: "2026-10-28T00:00:00Z", reviewed: null,
          },
          history: [{ id: "r1", status: "discrepancy", created_at: "2026-10-28T00:00:00Z", difference_count: 1, reviewed: false }],
        },
      }),
    });
    await page.goto("/en/trading/live/account");
    await expect(page.getByTestId("live-ledger-empty")).toContainText("no ledger entries yet");
    await expect(page.getByTestId("live-recon-ledger-empty")).toBeVisible();
    const latest = page.getByTestId("live-recon-latest");
    await expect(latest).toContainText("Differences found");
    await expect(page.getByTestId("live-recon-differences")).toContainText("exchange_vs_ledger");
    await expect(page.getByTestId("live-recon-differences")).toContainText("Δ 790");
    await expect(latest).toContainText("Only an administrator can review");
  });

  test("the account view fits a phone without horizontal page scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockLive(page, {
      ledger: () => ({ json: { account, entries: [entry(0), entry(1)], next_cursor: "c", limit: 50 } }),
      reconciliation: () => ({ json: { account, ledger: emptyLedgerSummary, latest: null, history: [] } }),
    });
    await page.goto("/en/trading/live/account");
    await expect(page.getByTestId("live-ledger-row")).toHaveCount(2);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
