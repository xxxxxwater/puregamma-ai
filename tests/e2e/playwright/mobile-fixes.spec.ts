import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";

const OUT = "../../.preview-round8";
mkdirSync(OUT, { recursive: true });
const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

test("mobile brand and api docs evidence", async ({ browser }) => {
  for (const [locale, path] of [["zh", "/zh"], ["en", "/en"]] as const) {
    for (const width of [320, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 800 } });
      await context.addInitScript((v) => { try { window.localStorage.setItem("pg_theme", v); } catch { /* ignore */ } }, "light");
      const page = await context.newPage();
      await page.route(`${API}/me`, (r) => r.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
      await page.route(`${API}/auth/x/config`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ x_login_enabled: false }) }));
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(2200);

      const brand = page.getByTestId("nav-brand");
      await expect(brand, `brand must exist on ${path} @${width}`).toBeVisible();
      const m = await brand.evaluate((el) => {
        const span = el.querySelector("span");
        const r = (span ?? el).getBoundingClientRect();
        const cs = getComputedStyle(span ?? el);
        return {
          text: (el.textContent || "").replace(/\s+/g, " ").trim(),
          w: Math.round(r.width),
          scrollW: (span ?? el).scrollWidth,
          clientW: (span ?? el).clientWidth,
          overflow: cs.overflow,
          textOverflow: cs.textOverflow,
          whiteSpace: cs.whiteSpace,
        };
      });
      const fullyVisible = m.scrollW <= m.clientW + 1 && m.textOverflow !== "ellipsis";
      console.log(`[${locale} ${width}] brand="${m.text}" box=${m.w} span scroll=${m.scrollW}/${m.clientW} overflow=${m.overflow} => ${fullyVisible ? "FULL" : "CLIPPED"}`);
      expect(m.text, "accessible name includes the full brand").toContain("PureGamma AI");
      expect(fullyVisible, `brand must not be clipped (${locale} @${width}): ${m.scrollW} > ${m.clientW}`).toBe(true);

      const header = await page.evaluate(() => {
        const row = document.querySelector("header.shell-chrome > div");
        return { scrollW: row ? row.scrollWidth : 0, clientW: row ? row.clientWidth : 0 };
      });
      expect(header.scrollW, "the header row itself must not overflow").toBeLessThanOrEqual(header.clientW + 1);

      await page.screenshot({ path: `${OUT}/brand-${locale}-${width}.png`, clip: { x: 0, y: 0, width, height: 90 } });
      await context.close();
    }
  }

  // API docs: widest content must scroll inside its own box, not widen the page.
  for (const width of [390, 430]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await page.goto("/zh/api", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);
    const r = await page.evaluate(() => {
      const doc = document.documentElement;
      const wrappers = Array.from(document.querySelectorAll("table")).map((t) => {
        const w = t.parentElement as HTMLElement;
        const cs = getComputedStyle(w);
        return { overflowX: cs.overflowX, scrolls: w.scrollWidth > w.clientWidth, tableW: Math.round(t.getBoundingClientRect().width), wrapperW: Math.round(w.clientWidth) };
      });
      return { doc: doc.clientWidth, scroll: doc.scrollWidth, wrappers };
    });
    console.log(`[api ${width}] doc=${r.scroll}/${r.doc} tables=${JSON.stringify(r.wrappers)}`);
    expect(r.scroll, "api docs must not widen the page").toBeLessThanOrEqual(r.doc + 1);
    for (const w of r.wrappers) expect(["auto", "scroll"], "each table sits in a scroll container").toContain(w.overflowX);
    await page.screenshot({ path: `${OUT}/api-docs-${width}.png`, fullPage: false });
    await context.close();
  }
});
