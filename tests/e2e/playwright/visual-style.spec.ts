import { expect, test, type Page } from "@playwright/test";

/**
 * Browser smoke for the self-authored glass visual system.
 *
 * - glass is the default visual style (pre-paint, via inline script);
 * - the Appearance control switches to classic and persists the choice in
 *   localStorage (pg_visual_style), never in the database;
 * - financial routes set data-surface-tier="financial" (high-opacity
 *   panels); ocean routes set "ocean" and disable the extra blur;
 * - dark/light theming keeps working on top of both visual styles.
 */

async function htmlDataset(page: Page) {
  return page.evaluate(() => ({
    visualStyle: document.documentElement.dataset.visualStyle ?? null,
    surfaceTier: document.documentElement.dataset.surfaceTier ?? null,
    theme: document.documentElement.dataset.theme ?? null,
  }));
}

async function backdropOf(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const element = document.querySelector(sel);
    if (!element) return null;
    return getComputedStyle(element).backdropFilter || getComputedStyle(element).webkitBackdropFilter || "none";
  }, selector);
}

test.describe("glass visual system", () => {
  test("glass is the default, toggles to classic, persists across reloads", async ({ page }) => {
    await page.goto("/en/options");

    // Default: glass, applied before paint by the inline root script.
    await expect(page.locator('html[data-visual-style="glass"]')).toHaveCount(1);
    // The shell chrome carries the shared backdrop filter.
    await expect.poll(() => backdropOf(page, "aside")).toContain("blur(");

    // Switch to classic through the Appearance control.
    await page.getByTitle("Switch to classic appearance").first().click();
    await expect(page.locator('html[data-visual-style="classic"]')).toHaveCount(1);
    expect(await page.evaluate(() => window.localStorage.getItem("pg_visual_style"))).toBe("classic");
    await expect.poll(() => backdropOf(page, "aside")).toBe("none");

    // The choice survives a full reload (pre-paint inline script).
    await page.reload();
    await expect(page.locator('html[data-visual-style="classic"]')).toHaveCount(1);

    // Switch back to glass for the remaining assertions.
    await page.getByTitle("Switch to glass appearance").first().click();
    await expect(page.locator('html[data-visual-style="glass"]')).toHaveCount(1);
    expect(await page.evaluate(() => window.localStorage.getItem("pg_visual_style"))).toBe("glass");
  });

  test("financial routes raise panel opacity; ocean routes skip double blur", async ({ page }) => {
    await page.goto("/en/portfolio");
    const financial = await htmlDataset(page);
    expect(financial.surfaceTier).toBe("financial");
    const panelOnFinancial = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--panel").trim()
    );
    expect(panelOnFinancial).toContain("0.93");

    await page.goto("/en/chat");
    const ocean = await htmlDataset(page);
    expect(ocean.surfaceTier).toBe("ocean");
    // Shell chrome still blurs (it is outside the Ocean work panel)...
    await expect.poll(() => backdropOf(page, "aside")).toContain("blur(");
    // ...but a content panel inside the Ocean page does not double-blur.
    const oceanPanelSelector = "main [class*='bg-bg-panel']";
    await expect(page.locator(oceanPanelSelector).first()).toBeVisible();
    await expect.poll(() => backdropOf(page, oceanPanelSelector)).toBe("none");
  });

  test("dark/light theming and font scale keep working with glass", async ({ page }) => {
    await page.goto("/en/options");
    // The theme attribute is applied by the AppearanceControls effect (not
    // pre-paint), so poll for it.
    await expect.poll(() => htmlDataset(page).then((d) => d.theme)).toBe("dark");

    await page.getByTitle("Toggle theme").first().click();
    expect((await htmlDataset(page)).theme).toBe("light");
    // Light glass tokens are active and the surface stays translucent.
    const panelLight = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--panel").trim()
    );
    expect(panelLight).toContain("0.64");
    await expect.poll(() => backdropOf(page, "aside")).toContain("blur(");

    await page.getByTitle("Increase text size").first().click();
    expect(await page.evaluate(() => document.documentElement.dataset.fontScale)).toBe("large");

    await page.getByTitle("Toggle theme").first().click();
    expect((await htmlDataset(page)).theme).toBe("dark");
  });
});
