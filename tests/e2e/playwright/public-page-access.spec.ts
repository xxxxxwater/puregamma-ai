import { expect, test, type Page } from "@playwright/test";

/**
 * Public pages must stay reachable while logged out.
 *
 * Regression: `lib/api.ts` dispatched the auth-expired event for *every* 401.
 * A logged-out visitor's landing page still issues authenticated reads (the
 * identity probe `GET /me` and the plugin catalog
 * `GET /api/frontend/plugins`), both of which answer 401 without a session.
 * The shell's watchdog treated that as an expired session and redirected to
 * `/zh/login?returnTo=%2F`, so the public homepage — and the DeepSeek V4.1
 * Flash preview card it renders — was invisible to every logged-out visitor
 * and to crawlers that execute JavaScript.
 *
 * The fix scopes the redirect to surfaces that actually require a session
 * (`lib/route-access.ts`, shared with `middleware.ts`). These specs pin both
 * halves: public pages stay put, protected pages still bounce to login.
 */

const PUBLIC_PATHS = ["/zh", "/en", "/zh/api"] as const;

/** Answer the two authenticated probes the way a logged-out browser sees them. */
async function stubLoggedOut(page: Page) {
  await page.route("**/me", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Authentication required" }) }),
  );
  await page.route("**/api/frontend/plugins*", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Authentication required" }) }),
  );
}

test.describe("logged-out visitors are not redirected off public pages", () => {
  for (const path of PUBLIC_PATHS) {
    test(`${path} stays put and keeps rendering`, async ({ page }) => {
      await stubLoggedOut(page);

      await page.goto(path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(4000); // give the auth watchdog time to fire

      expect(new URL(page.url()).pathname).toBe(path);
      expect(page.url()).not.toContain("/login");
    });
  }

  test("the homepage preview card reaches visitors without a session", async ({ page }) => {
    await stubLoggedOut(page);

    await page.goto("/zh", { waitUntil: "domcontentloaded" });
    const card = page.getByTestId("model-upgrade-preview");
    await expect(card).toBeVisible({ timeout: 20000 });

    // The badge must reflect the catalog the deployment serves, not the copy.
    await expect(card).toHaveAttribute("data-model-availability", /live|pending|unknown|unavailable/);
    await expect(card).toContainText("DeepSeek V4.1 Flash");
    await expect(page.getByTestId("model-announcement")).toContainText("DeepSeek V4.1 Flash");
  });
});

test.describe("protected surfaces still require a session", () => {
  // The Playwright webServer forces REQUIRE_AUTH=false so the suite can reach
  // signed-in surfaces. The middleware guard therefore cannot be exercised
  // here; run with REQUIRE_AUTH=true and an already-running server to check it.
  test.skip(
    process.env.REQUIRE_AUTH !== "true",
    "requires a server started with REQUIRE_AUTH=true",
  );

  for (const path of ["/zh/chat", "/zh/dashboard"] as const) {
    test(`${path} sends a logged-out visitor to login`, async ({ page }) => {
      await stubLoggedOut(page);

      await page.goto(path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);

      expect(page.url()).toContain("/login");
    });
  }
});
