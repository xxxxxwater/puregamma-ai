import { expect, test } from "@playwright/test";

/**
 * Browser-level smoke test for the Cordis frontend plugin runtime.
 *
 * The dev server has no API running, so the manifest request is intercepted
 * and fulfilled with a realistic FastAPI response. This verifies the whole
 * client pipeline: manifest fetch -> whitelist resolution -> builtin plugin
 * apply (panels/commands) -> clean disposal on shell unmount, with no
 * leftover realtime connections. Trading stays disabled (manifest-enabled
 * only) and third-party ids are never loaded.
 */

const manifest = {
  plugins: [
    { id: "puregamma.portfolio", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: ["portfolio_access"], permissions: ["read:portfolio"], routes: ["/portfolio"] },
    { id: "puregamma.research", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: ["agent_daily_runs"], permissions: ["read:research"], routes: ["/research", "/reports", "/backtest"] },
    { id: "puregamma.options", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: [], permissions: ["read:research"], routes: ["/options"] },
    { id: "puregamma.secretary", version: "1.0.0", enabled: true, entry: "builtin", required_entitlements: ["agent_daily_runs"], permissions: ["read:research"], routes: ["/secretary", "/chat"] },
    { id: "puregamma.trading", version: "1.0.0", enabled: false, entry: "builtin", required_entitlements: [], permissions: ["trade:paper"], routes: ["/trading/paper"] },
    // An id the API would never return; even if it did, it is not in the
    // compiled whitelist and must never execute.
    { id: "thirdparty.evil", version: "9.9.9", enabled: true, entry: "url", required_entitlements: [], permissions: [], routes: [] },
  ],
};

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

test.describe("Cordis frontend plugin runtime", () => {
  test("loads whitelisted builtin plugins from the manifest and disposes cleanly", async ({ page }) => {
    let manifestRequests = 0;
    await page.route("**/api/frontend/plugins", async (route) => {
      manifestRequests += 1;
      await route.fulfill({ json: manifest });
    });

    await page.goto("/en/dashboard");

    await expect(page.locator('[data-plugin-runtime="active"]')).toBeVisible();

    // React StrictMode double-invokes effects in dev, so tolerate 1-2 fetches.
    expect(manifestRequests).toBeGreaterThanOrEqual(1);
    await expect
      .poll(() => page.evaluate(() => window.__PUREGAMMA_PLUGIN_RUNTIME__?.loadedPlugins ?? []))
      .toContain("puregamma.portfolio");
    // Builtin plugins load through async dynamic imports: wait until the
    // whole whitelist set has applied before asserting the exact list.
    await expect
      .poll(() => page.evaluate(() => window.__PUREGAMMA_PLUGIN_RUNTIME__?.loadedPlugins.length ?? 0))
      .toBe(4);

    const state = await page.evaluate(() => window.__PUREGAMMA_PLUGIN_RUNTIME__);
    expect(state).toBeTruthy();
    expect(state!.loadedPlugins).toEqual([
      "puregamma.portfolio",
      "puregamma.research",
      "puregamma.options",
      "puregamma.secretary",
    ]);
    // trading stayed disabled (manifest) and the third-party id never loaded.
    expect(state!.loadedPlugins).not.toContain("puregamma.trading");
    expect(state!.loadedPlugins).not.toContain("thirdparty.evil");
    // Panels and commands registered by the loaded builtin plugins.
    expect(state!.panelIds).toContain("portfolio.overview");
    expect(state!.panelIds).toContain("research.console");
    expect(state!.panelIds).toContain("options.surface");
    expect(state!.panelIds).toContain("secretary.console");
    expect(state!.panelIds).not.toContain("trading.paper");
    expect(state!.commandIds).toContain("portfolio.refresh");
    expect(state!.commandIds).toContain("research.refresh");
    expect(state!.commandIds).toContain("secretary.refresh");
    expect(state!.realtimeConnections).toBe(0);

    // Unmount the shell: /privacy lives OUTSIDE the [locale] tree. Use a
    // client-side soft navigation (Next dev exposes window.next.router) so the
    // unmount happens in THIS window and the diagnostics stay observable —
    // a hard page.goto would destroy the window before the flag is readable.
    await page.evaluate(() => {
      const router = (window as unknown as { next?: { router?: { push: (url: string) => void } } }).next?.router;
      if (!router) throw new Error("window.next.router not available in dev server");
      router.push("/privacy");
    });
    await expect(page.locator('[data-plugin-runtime="active"]')).toHaveCount(0);
    await expect
      .poll(() => page.evaluate(() => window.__PUREGAMMA_PLUGIN_RUNTIME__?.disposed ?? false))
      .toBe(true);
    const afterDispose = await page.evaluate(() => window.__PUREGAMMA_PLUGIN_RUNTIME__);
    expect(afterDispose!.realtimeConnections).toBe(0);
  });
});
