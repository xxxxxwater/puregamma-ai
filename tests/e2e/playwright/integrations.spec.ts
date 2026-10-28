import { expect, test } from "@playwright/test";

/**
 * /integrations lists the user's real read-only connections, read on the
 * server from /portfolio (fixtures/ssr-api.mjs).
 *
 * This spec used to expect a fixed set of demo connectors ("Plaid Brokerage",
 * "Binance Read-only", Telegram, iMessage). The page no longer substitutes demo
 * connectors for real status: with no data it says the status is unavailable,
 * and signed in it shows exactly the connections the API returned.
 */
const FIXTURE_SESSION = "playwright-fixture-session";

test.describe("/integrations", () => {
  test("without connection data it shows the security notice and no demo connectors", async ({ page }) => {
    await page.goto("/en/integrations");

    await expect(page.getByRole("heading", { name: "Portfolio Source Connections" })).toBeVisible();
    await expect(page.getByText("Use read-only API keys only.").first()).toBeVisible();
    await expect(page.getByText("Never provide withdrawal permissions or private keys.").first()).toBeVisible();
    await expect(page.getByText("Connection status unavailable")).toBeVisible();
    await expect(page.getByText("Demo connectors will not be substituted for real status.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Plaid Brokerage" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Binance Read-only" })).toHaveCount(0);
  });

  test("signed in, it shows exactly the connections the API returned", async ({ page, baseURL }) => {
    await page.context().addCookies([{ name: "pg_session", value: FIXTURE_SESSION, url: baseURL ?? "http://127.0.0.1:3000" }]);
    await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
    await page.route("**/__dev-api/me", (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u-int", email: "int@example.invalid", name: "Int", role: "user", plan: "Pro", credit_balance: 10, auth_provider: "email" } }) }),
    );

    await page.goto("/en/integrations");

    await expect(page.getByText("Connection status unavailable")).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 3 })).toHaveText(["Fixture Brokerage", "Fixture Hyperliquid"]);
    await expect(page.getByText("PLAID read-only portfolio connection")).toBeVisible();
    // A failing connection reports its own error rather than looking healthy.
    await expect(page.getByText("Address returned no account state.")).toBeVisible();
    await expect(page.getByText("not synchronized")).toBeVisible();
    await expect(page.getByRole("link", { name: "Connect" }).first()).toHaveAttribute("href", "/en/portfolio");
  });
});
