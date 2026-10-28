import { expect, test } from "@playwright/test";

/**
 * The MSTR–BTC research view (`/[locale]/opportunities/mstr-btc`).
 *
 * This spec used to assert a full dashboard (Strategy.com provenance, scenario
 * inputs, "Ask Agent" handoff). That page is not part of this codebase: no
 * revision of apps/web ever contained an `opportunities` route — only the spec
 * arrived, in a production-state sync — and the "Opportunities" navigation
 * item was removed with the rest of that surface. Asserting a page that does
 * not exist can only fail, so the spec now pins the current contract: the
 * address answers an honest 404 and renders no half-built research view. If
 * the view is (re)introduced, restore the dashboard assertions with it.
 */
test.describe("MSTR–BTC dashboard (not shipped)", () => {
  for (const locale of ["en", "zh"] as const) {
    test(`the retired address answers 404 without a partial research view (${locale})`, async ({ page }) => {
      const response = await page.goto(`/${locale}/opportunities/mstr-btc`);

      expect(response?.status()).toBe(404);
      await expect(page.getByText(/404/).first()).toBeVisible();
      await expect(page.getByRole("heading", { name: "MSTR–BTC Dashboard" })).toHaveCount(0);
      await expect(page.getByLabel(/BTC price assumption/)).toHaveCount(0);
    });
  }
});
