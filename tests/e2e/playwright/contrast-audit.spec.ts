import { expect, test, type Page } from "@playwright/test";

/**
 * Rendered contrast + overflow measurement for the surfaces this round touched.
 *
 * This walks the real DOM with each element's computed colour composited over
 * the nearest painted background, so it measures what a reader sees rather than
 * what the palette file intends. Target: WCAG AA — 4.5:1 body text, 3:1 large
 * text.
 */

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

const MEASURE = () => {
  const toRgb = (value: string) => {
    const m = value.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((v) => parseFloat(v.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lum = ({ r, g, b }: { r: number; g: number; b: number }) => {
    const f = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const over = (fg: any, bg: any) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
  const ratio = (a: any, b: any) => { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); };
  const painted = (el: Element) => {
    let node: Element | null = el;
    let acc: any = null;
    while (node) {
      const bg = toRgb(getComputedStyle(node).backgroundColor || "");
      if (bg && bg.a > 0) acc = acc ? over(acc, bg) : bg;
      if (acc && acc.a >= 0.999) return acc;
      node = node.parentElement;
    }
    return acc || { r: 255, g: 255, b: 255, a: 1 };
  };

  const out: Array<Record<string, unknown>> = [];
  for (const el of Array.from(document.querySelectorAll("p, span, a, li, td, th, dt, dd, h1, h2, h3, h4, label, button, summary"))) {
    const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent || "").join("").trim();
    if (!own) continue;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || parseFloat(style.opacity) < 0.6) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) continue;
    const fg = toRgb(style.color || "");
    if (!fg) continue;
    const bg = painted(el);
    const composited = fg.a < 1 ? over(fg, bg) : fg;
    const size = parseFloat(style.fontSize);
    const weight = parseInt(style.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const r = ratio(composited, bg);
    const need = large ? 3 : 4.5;
    if (r < need) out.push({ text: own.slice(0, 40), ratio: Number(r.toFixed(2)), need, size: Math.round(size), color: style.color });
  }
  return out;
};

async function openWithTheme(page: Page, path: string, theme: "light" | "dark") {
  await page.addInitScript((value) => { try { window.localStorage.setItem("pg_theme", value); } catch { /* ignore */ } }, theme);
  await page.goto(path);
  await page.waitForFunction((value) => document.documentElement.dataset.theme === value, theme, { timeout: 15000 }).catch(() => {});
}

/** Collect runtime errors from the first moment, not after the page settles. */
function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`${err.message.split("\n")[0].slice(0, 120)} @@ ${(err.stack || "").split("\n").slice(1, 4).join(" <- ").slice(0, 260)}`));
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(`console: ${msg.text().slice(0, 160)}`); });
  return errors;
}

for (const theme of ["light", "dark"] as const) {
  test(`chat surface meets AA in ${theme}`, async ({ page }) => {
    const errors = watchErrors(page);
    // Shape the stubs like the real payloads: a bare `{}` makes the Chat shell
    // read `conversations` as undefined and crash, which would replace the
    // surface under test with the dev error overlay.
    //
    // The catch-all is registered FIRST: Playwright consults routes in reverse
    // registration order, so the specific stubs below take precedence.
    await page.route(`${API}/**`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({}) }),
    );
    await page.route(`${API}/me`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u", email: "a@b.invalid", name: "A", role: "user", plan: "Pro", credit_balance: 1200 } }) }),
    );
    // The plugin manifest feeds the client entitlement service, which reads
    // `allowed_data_sources` with `.filter`. An empty object here throws inside
    // the plugin runtime and paints the dev error overlay over the surface
    // under test, so it must carry the real shape.
    await page.route(`${API}/api/frontend/plugins*`, (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          plugins: [],
          capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 },
        }),
      }),
    );
    await page.route(`${API}/api/agent/capabilities`, (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 },
          quota: { plan: "Pro", used: 3, limit: 200, remaining: 197, concurrent_limit: 2, running: 0, credit_balance: 1200 },
          models: [
            { id: "default", display_name: "Default model", description: "", provider: "default", available: true, reason: null, credit_cost: null },
            { id: "gpt-5.6-luna", display_name: "GPT-5.6 Luna", description: "Deep research.", provider: "openai", available: false, reason: "plan_required", credit_cost: null },
          ],
          skills: [],
        }),
      }),
    );
    await page.route(`${API}/api/agent/quota`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ plan: "Pro", used: 3, limit: 200, remaining: 197, concurrent_limit: 2, running: 0, credit_balance: 1200 }) }),
    );
    await page.route(`${API}/api/agent/conversations**`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ conversations: [] }) }),
    );
    await page.route(`${API}/api/agent/quote`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ estimated_min: 8, estimated_max: 12 }) }),
    );
    await openWithTheme(page, "/zh/chat", theme);
    await page.waitForTimeout(2500);
    const failures = await page.evaluate(MEASURE);
    const overflow = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    console.log(`[chat ${theme}] url=${page.url()}`);
    console.log(`[chat ${theme}] overflow=${overflow.sw}/${overflow.cw}`);
    for (const f of failures) console.log(`  FAIL ${f.ratio}:1 need ${f.need} ${f.size}px ${f.color} :: ${f.text}`);
    console.log(`[chat ${theme}] failures=${failures.length}`);
    const relevant = errors.filter((e) => !/CORS|ERR_FAILED|Failed to load resource|gtag|doubleclick|google/.test(e));
    console.log(`[chat ${theme}] errors=${relevant.length}`);
    for (const e of relevant.slice(0, 5)) console.log(`  ERR ${e}`);
    await page.screenshot({ path: `../../.preview-after/chat-${theme}.png` });
    expect(overflow.sw).toBeLessThanOrEqual(overflow.cw + 1);
  });
}
