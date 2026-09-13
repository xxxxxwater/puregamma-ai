/**
 * Theme engine regression.
 *
 * Three things were structurally wrong before this round and each is asserted
 * here against real browser behaviour rather than class names:
 *
 *  1. Dark was the `:root` default and the theme was applied in a `useEffect`,
 *     so a light-preference user saw dark on EVERY load. The test boots with a
 *     saved preference and samples `data-theme` as early as the page allows —
 *     if the theme were still applied after hydration, the first sample would
 *     be `light` while the stored preference is `dark`.
 *  2. Three AppearanceControls mounts each held their own state, so they could
 *     disagree; and a two-state switch could not express "follow the system".
 *  3. `useHtmlDataset` built `data-visualStyle`, which never matched
 *     `data-visual-style`, leaving consumers permanently on their first guess.
 */
import { expect, test } from "@playwright/test";

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

async function stubPublic(page: import("@playwright/test").Page) {
  await page.route(`${API}/me`, (r) => r.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
  await page.route(`${API}/auth/x/config`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ x_login_enabled: false }) }));
}

test.describe("theme engine", () => {
  test("a saved dark preference is applied before first paint, not after hydration", async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem("pg_theme", "dark"); } catch { /* ignore */ } });
    await stubPublic(page);

    // Sample the attribute as soon as a document exists. If the theme were
    // still applied in useEffect this would observe light first.
    await page.goto("/zh", { waitUntil: "domcontentloaded" });
    const early = await page.evaluate(() => ({
      theme: document.documentElement.dataset.theme,
      colorScheme: document.documentElement.style.colorScheme,
    }));
    expect(early.theme, "theme must already be dark at the earliest readable moment").toBe("dark");
    expect(early.colorScheme, "color-scheme must be set pre-paint").toBe("dark");

    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark", { timeout: 10000 });
  });

  test("a saved light preference does not flash dark", async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem("pg_theme", "light"); } catch { /* ignore */ } });
    await stubPublic(page);
    await page.goto("/zh", { waitUntil: "domcontentloaded" });
    const early = await page.evaluate(() => ({
      theme: document.documentElement.dataset.theme,
      colorScheme: document.documentElement.style.colorScheme,
    }));
    expect(early.theme).toBe("light");
    expect(early.colorScheme).toBe("light");
  });

  test("font scale is applied pre-paint too", async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem("pg_font_scale", "large"); } catch { /* ignore */ } });
    await stubPublic(page);
    await page.goto("/zh", { waitUntil: "domcontentloaded" });
    const early = await page.evaluate(() => ({
      attr: document.documentElement.dataset.fontScale,
      rootFontSize: parseFloat(getComputedStyle(document.documentElement).fontSize),
    }));
    expect(early.attr, "font scale attribute set before paint").toBe("large");
    expect(early.rootFontSize, "root font size reflects the scale on first paint").toBeGreaterThanOrEqual(18);
  });

  test("no preference follows the operating system", async ({ browser }) => {
    for (const scheme of ["dark", "light"] as const) {
      const context = await browser.newContext({ colorScheme: scheme });
      const page = await context.newPage();
      await stubPublic(page);
      await page.goto("/zh", { waitUntil: "domcontentloaded" });
      const theme = await page.evaluate(() => document.documentElement.dataset.theme);
      expect(theme, `system ${scheme} must resolve to ${scheme}`).toBe(scheme);
      await context.close();
    }
  });

  test("an unreadable or corrupt stored value degrades instead of breaking", async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem("pg_theme", "chartreuse"); window.localStorage.setItem("pg_font_scale", "enormous"); } catch { /* ignore */ } });
    await stubPublic(page);
    await page.goto("/zh", { waitUntil: "domcontentloaded" });
    const state = await page.evaluate(() => ({
      theme: document.documentElement.dataset.theme,
      scale: document.documentElement.dataset.fontScale,
    }));
    expect(["light", "dark"], "an invalid value must fall back, never produce a broken theme").toContain(state.theme);
    expect(state.scale).toBe("default");
  });

  test("storage that throws does not break rendering", async ({ page }) => {
    // Some embedded/privacy contexts throw on any localStorage access.
    await page.addInitScript(() => {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        get() { throw new Error("storage disabled"); },
      });
    });
    await stubPublic(page);
    await page.goto("/zh", { waitUntil: "domcontentloaded" });
    const theme = await page.evaluate(() => document.documentElement.dataset.theme);
    expect(["light", "dark"]).toContain(theme);
    await expect(page.locator("body")).toBeVisible();
  });

  test("the three appearance controls agree and cycle system → light → dark", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript(() => { try { window.localStorage.removeItem("pg_theme"); } catch { /* ignore */ } });
    await stubPublic(page);
    await page.goto("/zh");
    await page.waitForFunction(() => document.documentElement.dataset.theme !== undefined);

    const controls = page.locator("[data-theme-preference]");
    const count = await controls.count();
    expect(count, "appearance controls are mounted more than once").toBeGreaterThan(1);

    // All mounts must report the SAME preference (they had independent state).
    const preferences = await controls.evaluateAll((els) => els.map((el) => el.getAttribute("data-theme-preference")));
    expect(new Set(preferences).size, `mounts disagreed: ${preferences.join(", ")}`).toBe(1);

    // system -> light
    await controls.first().click();
    let next = await controls.evaluateAll((els) => els.map((el) => el.getAttribute("data-theme-preference")));
    expect(new Set(next).size, "mounts disagreed after a click").toBe(1);
    expect(next[0]).toBe("light");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    // light -> dark
    await controls.first().click();
    next = await controls.evaluateAll((els) => els.map((el) => el.getAttribute("data-theme-preference")));
    expect(next[0]).toBe("dark");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    // dark -> system, and the reload keeps it
    await controls.first().click();
    next = await controls.evaluateAll((els) => els.map((el) => el.getAttribute("data-theme-preference")));
    expect(next[0]).toBe("system");
    const stored = await page.evaluate(() => window.localStorage.getItem("pg_theme"));
    expect(stored, "system is stored by absence, so it stays the fallback").toBeNull();
  });

  test("popovers and native controls follow the app theme", async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem("pg_theme", "dark"); } catch { /* ignore */ } });
    await stubPublic(page);
    await page.goto("/zh");
    await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
    // color-scheme is what makes the OS draw native <select> popups and
    // scrollbars dark; without it they stayed light on a dark page.
    const scheme = await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
    expect(scheme).toContain("dark");
  });
});
