import { expect, test, type Page } from "@playwright/test";

/**
 * Every localized route, with the API unavailable.
 *
 * The browser API answers 503 for everything except the signed-in user, and the
 * dev proxy points at a closed port, so server-side fetches fail too. That is
 * the "provider missing / outage" case every page must survive: it may show an
 * unavailable state, but it must not throw, must not fall into the error
 * boundary, must not scroll sideways on a phone, and every button or link it
 * renders must have an accessible name.
 */

const ROUTES = [
  "/", "/account", "/admin", "/admin/billing-intents", "/admin/gateway", "/admin/stripe-events", "/api",
  "/backtest", "/billing", "/billing/cancel", "/billing/success", "/chat", "/chat/c-audit", "/daily-push",
  "/dashboard", "/data-sources", "/docs", "/forgot-password", "/gateway", "/integrations", "/jev-trader",
  "/login", "/memory", "/mobile-access", "/nautilus", "/news", "/onboarding/assets", "/onboarding/channels",
  "/onboarding/style", "/options", "/playbooks", "/portfolio", "/pricing", "/reports", "/research",
  "/research/r-audit", "/reset-password", "/secretary", "/signals", "/signup", "/strategies",
  "/strategies/s-audit", "/trading/live", "/trading/live/account", "/trading/live/connect",
  "/trading/live/orders", "/trading/paper", "/trading/positions", "/trading/risk", "/trading/runtime",
  "/verify-email",
];

async function apiDown(page: Page) {
  await page.route("**/__dev-api/**", (route) => {
    const url = route.request().url();
    if (/\/me(\?|$)/.test(url)) {
      return route.fulfill({ json: { user: { id: "u-audit", email: "audit@example.invalid", name: "Audit", role: "user", plan: "Pro", credit_balance: 0, auth_provider: "email" } } });
    }
    return route.fulfill({ status: 503, json: { detail: "unavailable" } });
  });
}

async function unnamedControls(page: Page) {
  return page.evaluate(() => {
    const visible = (el: Element) => {
      const box = (el as HTMLElement).getBoundingClientRect();
      const style = getComputedStyle(el);
      return box.width > 0 && box.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const name = (el: Element) =>
      (el.getAttribute("aria-label") || "").trim() ||
      (el.getAttribute("aria-labelledby") ? "labelled" : "") ||
      (el.getAttribute("title") || "").trim() ||
      (el.textContent || "").trim() ||
      Array.from(el.querySelectorAll("img[alt]")).map((img) => img.getAttribute("alt") || "").join("").trim();
    return Array.from(document.querySelectorAll("button, a[href], [role='button']"))
      .filter((el) => visible(el) && !name(el))
      .slice(0, 5)
      .map((el) => el.outerHTML.slice(0, 160));
  });
}

for (const locale of ["en", "zh"] as const) {
  test.describe(`every route survives an API outage (${locale})`, () => {
    for (const route of ROUTES) {
      // Chinese runs a representative subset; the layout is shared.
      if (locale === "zh" && !["/", "/chat", "/dashboard", "/portfolio", "/trading/live/orders", "/research"].includes(route)) continue;
      test(`${locale}${route}`, async ({ page }, info) => {
        test.setTimeout(120_000);
        const errors: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await apiDown(page);
        await page.goto(`/${locale}${route === "/" ? "" : route}`, { waitUntil: "domcontentloaded", timeout: 90_000 });
        await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
        await page.waitForTimeout(500);

        await expect(page.getByTestId("route-error"), "fell into the error boundary").toHaveCount(0);
        expect(errors, "uncaught page errors").toEqual([]);

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, "page scrolls sideways").toBeLessThanOrEqual(1);

        expect(await unnamedControls(page), "buttons/links without an accessible name").toEqual([]);
        if (info.project.name === "mobile-chrome" && locale === "en") {
          await page.screenshot({ path: info.outputPath(`${route.replace(/\//g, "_") || "root"}.png`) });
        }
      });
    }
  });
}
