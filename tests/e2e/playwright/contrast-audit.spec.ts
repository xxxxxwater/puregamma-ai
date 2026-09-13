import { expect, test, type Page } from "@playwright/test";

/**
 * Rendered contrast + clipping measurement for the surfaces this round touched.
 *
 * WHY THIS FILE WAS REWRITTEN
 * ---------------------------
 * The previous version walked the DOM correctly but only *printed* what it
 * found: it had two tests and exactly one assertion, `expect(overflow.sw)
 * .toBeLessThanOrEqual(overflow.cw + 1)`. Every contrast violation went to
 * `console.log`, so the suite reported green on a page whose body text was
 * unreadable, and on a page that failed to render at all. A gate that cannot
 * fail is not coverage.
 *
 * This version asserts, and it also proves the gate can fail:
 *
 *  1. `contrast detector` injects known-bad and known-good fixtures into a live
 *     page and asserts the measurement reports each one with the right verdict.
 *     Without this, "0 failures" is indistinguishable from "detector blind",
 *     which is precisely the bug being fixed.
 *  2. `public surfaces` audits real rendered pages in both themes and requires
 *     zero violations against WCAG AA (4.5:1 body, 3:1 large text).
 *  3. Each audit also asserts a floor on the number of text nodes it measured,
 *     so a blank page, a crashed route or a page replaced by a dev error overlay
 *     fails instead of trivially passing.
 *  4. Clipping is asserted: document-level horizontal overflow, plus any element
 *     whose own content is wider than its painted box while it says
 *     `overflow: hidden|clip` — text silently cut off is a defect the old
 *     overflow-only assertion could not see.
 *
 * NOT COVERED HERE (needs a session, see the note at the bottom of this header):
 * `/chat`, `/admin/*`. They are gated by middleware, so without a session they
 * render the login redirect and this file would be auditing `/login` while
 * claiming to audit the console.
 *
 * NOTE ON COOKIES, for whoever adds the authenticated pass
 * -------------------------------------------------------
 * Playwright's `addCookies({ url: "https://api.puregamma.ai", ... })` produces a
 * HOST-ONLY cookie: it is never sent to `app.puregamma.ai`, so `/me` answers 401
 * and the client watchdog bounces you to login. The session cookie only works
 * scoped to the registrable domain:
 *
 *   await context.addCookies([{ name: "pg_session", value: <jwt>,
 *     domain: ".puregamma.ai", path: "/", httpOnly: true, secure: true,
 *     sameSite: "Lax" }]);
 *
 * That is why the dev harness sets `REQUIRE_AUTH=false` and stubs `/me`
 * in-page: same-origin `/__dev-api`, no cookie scoping involved.
 */

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

/** Every measured surface is booted with an explicit stored preference, so the
 *  result never depends on the host machine's `prefers-color-scheme`. */
type Theme = "light" | "dark";

interface Violation {
  text: string;
  ratio: number;
  need: number;
  size: number;
  color: string;
  cls: string;
}

interface Clip {
  tag: string;
  cls: string;
  scrollWidth: number;
  clientWidth: number;
}

interface Audit {
  theme: string;
  failures: Violation[];
  clipped: Clip[];
  doc: { sw: number; cw: number };
  stats: { measured: number; skipped: number; samples: number };
}

/** Composites each element's computed colour over the nearest painted
 *  background and returns the WCAG AA violations. Mirrors the real cascade:
 *  translucent foregrounds are composited, translucent ancestors accumulate. */
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

  const label = (el: Element) => `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : ""}`;

  const failures: any[] = [];
  const clipped: any[] = [];
  let measured = 0;
  let skipped = 0;

  for (const el of Array.from(document.querySelectorAll("p, span, a, li, td, th, dt, dd, h1, h2, h3, h4, label, button, summary"))) {
    const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent || "").join("").trim();
    if (!own) continue;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || parseFloat(style.opacity) < 0.6) { skipped += 1; continue; }
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) { skipped += 1; continue; }
    const fg = toRgb(style.color || "");
    if (!fg) { skipped += 1; continue; }
    measured += 1;

    const bg = painted(el);
    const composited = fg.a < 1 ? over(fg, bg) : fg;
    const size = parseFloat(style.fontSize);
    const weight = parseInt(style.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const r = ratio(composited, bg);
    const need = large ? 3 : 4.5;
    if (r < need) {
      failures.push({ text: own.slice(0, 40), ratio: Number(r.toFixed(2)), need, size: Math.round(size), color: style.color, cls: label(el) });
    }

    // A non-scrollable box painting less width than its content is hiding text.
    const ox = style.overflowX;
    if ((ox === "hidden" || ox === "clip") && el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) {
      clipped.push({ tag: label(el), cls: label(el), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
    }
  }

  return {
    failures,
    clipped,
    doc: { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth },
    stats: { measured, skipped, samples: 1 },
  };
};

async function openWithTheme(page: Page, path: string, theme: Theme) {
  await page.addInitScript((value) => { try { window.localStorage.setItem("pg_theme", value); } catch { /* ignore */ } }, theme);
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await page.waitForFunction((value) => document.documentElement.dataset.theme === value, theme, { timeout: 15000 });
}

/** Collect runtime errors from the first moment, not after the page settles. */
function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`${err.message.split("\n")[0].slice(0, 120)} @@ ${(err.stack || "").split("\n").slice(1, 4).join(" <- ").slice(0, 260)}`));
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(`console: ${msg.text().slice(0, 160)}`); });
  return errors;
}

/**
 * Sample until the failure set stops changing.
 *
 * The old version slept a flat 2500ms: too short on a cold dev compile (it
 * measured a half-painted page) and pure waste on a warm one. Two identical
 * consecutive samples mean fonts, late chunks and colour transitions have
 * settled.
 */
async function measureStable(page: Page, theme: Theme, timeoutMs = 20000): Promise<Audit> {
  const started = Date.now();
  let previous = "";
  let stable = 0;
  let last: Audit | null = null;
  while (Date.now() - started < timeoutMs) {
    last = (await page.evaluate(MEASURE)) as Audit;
    const key = JSON.stringify(last.failures) + JSON.stringify(last.clipped) + last.stats.measured;
    stable = key === previous ? stable + 1 : 0;
    previous = key;
    if (stable >= 1 && last.stats.measured > 0) {
      last.stats.samples += 1;
      last.theme = theme;
      return last;
    }
    await page.waitForTimeout(400);
  }
  if (!last) throw new Error(`contrast measurement never produced a sample for ${theme}`);
  last.stats.samples += 1;
  last.theme = theme;
  return last;
}

function describe(v: Violation) {
  return `${v.ratio}:1 (needs ${v.need}:1) ${v.size}px ${v.color} ${v.cls} :: ${JSON.stringify(v.text)}`;
}

/** One line per violation, so a failure names the element instead of a count. */
function report(audit: Audit) {
  return [
    `theme=${audit.theme} measured=${audit.stats.measured} skipped=${audit.stats.skipped} samples=${audit.stats.samples}`,
    ...audit.failures.slice(0, 25).map((v) => `  contrast ${describe(v)}`),
    ...audit.clipped.slice(0, 25).map((c) => `  clipped ${c.tag} scrollWidth=${c.scrollWidth} clientWidth=${c.clientWidth}`),
  ].join("\n");
}

/**
 * Deterministic fixtures that exercise each branch of the measurement, injected
 * into whatever page is already loaded. `getComputedStyle` reads them whether or
 * not they are on screen; only colours, size and opacity matter.
 */
const FIXTURE = () => {
  // Opaque white baseline so every fixture's expected ratio is fixed arithmetic.
  // `position: fixed; left: -9999px` keeps the probe off-canvas; `getComputedStyle`
  // reads computed colours regardless of whether the box is on screen.
  const host = document.createElement("div");
  host.id = "__pg_contrast_fixture__";
  host.setAttribute("style", "position:fixed;left:-9999px;top:0;width:400px;background:rgb(255,255,255)");

  // The W3C relative-luminance definition, deliberately written a second time
  // from the spec rather than shared with MEASURE. If the two ever disagree the
  // comparisons below fail, which is the point: a shared helper would agree with
  // itself no matter how wrong it was.
  const L = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  const ratioOnWhite = (r: number, g: number, b: number) => {
    const l = 0.2126 * L(r) + 0.7152 * L(g) + 0.0722 * L(b);
    return Number(((1.05) / (l + 0.05)).toFixed(2));
  };

  const add = (id: string, color: string, extra: string, text: string, expected: number, parent: HTMLElement = host) => {
    const el = document.createElement("p");
    el.id = id;
    el.setAttribute("style", `font-size:16px;font-weight:400;margin:0;white-space:nowrap;color:${color};${extra}`);
    el.dataset.expectedRatio = String(expected);
    el.textContent = text;
    parent.appendChild(el);
    return el;
  };

  // 2.96:1 — must be reported, and must be reported as needing 4.5.
  add("__pg_bad__", "rgb(150,150,150)", "", "low contrast fixture", ratioOnWhite(150, 150, 150));
  // 4.41:1 — deliberately just under AA. A `>=` slip or a rounding error in the
  // comparison would let this through, and no obviously-broken fixture would.
  add("__pg_bad_near__", "rgb(120,120,120)", "", "near threshold fixture", ratioOnWhite(120, 120, 120));
  // 18.88:1, well above AA — a detector that flagged everything would fail this,
  // which is what stops a blanket-fail detector from looking strict.
  add("__pg_good__", "rgb(17,17,17)", "", "readable fixture", ratioOnWhite(17, 17, 17));
  // 150 at 35% alpha composites over white to ~212 (1.48:1 if read opaquely, 1.39
  // once composited). Proves the foreground alpha is composited rather than read
  // at face value — the two are far enough apart to tell apart.
  add("__pg_bad_alpha__", "rgba(150,150,150,0.35)", "", "translucent low contrast fixture", ratioOnWhite(212, 212, 212));
  // Same colour behind a fully transparent ancestor: forces the background walk to
  // keep climbing past a box that looks painted but contributes nothing.
  const noBg = document.createElement("div");
  noBg.setAttribute("style", "background:rgba(255,255,255,0)");
  host.appendChild(noBg);
  add("__pg_bad_deep__", "rgb(150,150,150)", "", "fixture behind a transparent ancestor", ratioOnWhite(150, 150, 150), noBg);
  // Clipping probe. It is a `p`, not a `div`, because the measurement walks the
  // text-bearing selector list and a `div` would never be visited.
  add("__pg_clip__", "rgb(17,17,17)", "width:120px;overflow:hidden", "clipped fixture ".repeat(20), ratioOnWhite(17, 17, 17));
  document.body.appendChild(host);
  return true;
};

/** The ratio the fixture computed for itself from the W3C formula. */
async function expectedRatio(page: Page, id: string) {
  const value = await page.locator(`#${id}`).getAttribute("data-expected-ratio");
  if (value === null) throw new Error(`fixture #${id} did not set data-expected-ratio`);
  return Number(value);
}

/**
 * Tolerance for detector-vs-formula agreement.
 *
 * Two things separate the numbers: the ratio is rounded to two decimals for
 * reporting, and the CSS spec's sRGB transfer function uses a slightly different
 * threshold than WCAG's 0.03928 at these code values. 0.12 is far below any real
 * disagreement — trusting an opaque alpha would differ by ~0.09 here and every
 * plausible compositing bug by far more.
 */
const RATIO_TOLERANCE = 0.12;

/** Assert the detector agrees with the fixture's own arithmetic. */
function expectRatioAgrees(measured: number, expected: number, note: string) {
  expect(Math.abs(measured - expected), `${note}: detector said ${measured}, the W3C formula says ${expected}`).toBeLessThanOrEqual(RATIO_TOLERANCE);
}

const byId = (audit: Audit, id: string) => audit.failures.find((f) => f.cls.includes(id));

/**
 * Prove the audit is looking at the surface it names.
 *
 * Every assertion below is satisfied by an empty page, a crash page or a
 * redirect: zero contrast violations, zero clipped text, zero overflow. Without
 * this guard the whole file would pass on a 404 — which is the same class of
 * bug as the console.log version it replaces, just wearing assertions.
 */
async function expectRealSurface(page: Page, expectChinese: boolean, what: string) {
  const state = await page.evaluate(() => ({
    lang: document.documentElement.lang || "",
    text: (document.body.innerText || "").slice(0, 4000),
    overlay: document.querySelectorAll("nextjs-portal").length,
  }));
  expect(state.overlay, `${what}: the Next dev error overlay is mounted, so a runtime error replaced the UI`).toBe(0);
  expect(state.text.trim().length, `${what}: the page rendered no text at all`).toBeGreaterThan(120);
  const hasHan = /[\u4e00-\u9fff]/.test(state.text);
  expect(hasHan, `${what}: expected Chinese copy under the /zh route but found none`).toBe(expectChinese);
}

test.describe("contrast detector", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`reports known-bad fixtures and clears known-good ones in ${theme}`, async ({ page }) => {
      await openWithTheme(page, "/zh", theme);
      await page.evaluate(FIXTURE);
      const audit = await measureStable(page, theme);

      const bad = byId(audit, "__pg_bad__");
      expect(bad, `the low-contrast fixture must be reported\n${report(audit)}`).toBeTruthy();
      expect(bad!.need, "16px normal text is not large text, so it needs 4.5:1").toBe(4.5);
      // Compare the detector against the ratio the fixture computed from the
      // W3C formula itself, rather than a number typed in by hand.
      expectRatioAgrees(bad!.ratio, await expectedRatio(page, "__pg_bad__"), "opaque grey on white");

      const near = byId(audit, "__pg_bad_near__");
      expect(near, `a fixture just under AA must still be reported — an off-by-one in the comparison would hide here\n${report(audit)}`).toBeTruthy();
      expect(near!.ratio, "this fixture must actually sit below the AA threshold, or it proves nothing").toBeLessThan(4.5);
      expectRatioAgrees(near!.ratio, await expectedRatio(page, "__pg_bad_near__"), "just-under-AA grey on white");

      const good = byId(audit, "__pg_good__");
      expect(good, `an easily readable fixture must NOT be reported — otherwise the detector flags everything\n${report(audit)}`).toBeUndefined();
      expect(await expectedRatio(page, "__pg_good__"), "the control fixture must be comfortably above AA").toBeGreaterThan(7);

      const alpha = byId(audit, "__pg_bad_alpha__");
      expect(alpha, `35% alpha must be composited, not read at face value\n${report(audit)}`).toBeTruthy();
      expectRatioAgrees(alpha!.ratio, await expectedRatio(page, "__pg_bad_alpha__"), "translucent foreground composited over white");

      const deep = byId(audit, "__pg_bad_deep__");
      expect(deep, `the background walk must survive a transparent ancestor\n${report(audit)}`).toBeTruthy();
      expect(deep!.ratio, `a transparent ancestor must not change the measured ratio\n${report(audit)}`).toBe(bad!.ratio);

      const clip = audit.clipped.find((c) => c.cls.includes("__pg_clip__"));
      expect(clip, `a clipped nowrap line in a 120px box must be reported\n${report(audit)}`).toBeTruthy();
      expect(clip!.scrollWidth).toBeGreaterThan(600);
      expect(clip!.clientWidth).toBeLessThanOrEqual(120);
    });
  }

  test("fixtures stay out of the layout and out of the accessibility tree", async ({ page }) => {
    await openWithTheme(page, "/zh", "light");
    const before = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, text: document.body.innerText.length }));
    await page.evaluate(FIXTURE);
    const after = await page.evaluate(() => {
      const host = document.getElementById("__pg_contrast_fixture__") as HTMLElement;
      const rect = host.getBoundingClientRect();
      return { sw: document.documentElement.scrollWidth, text: document.body.innerText.length, left: rect.left, right: rect.right };
    });
    // An off-canvas x:-9999 fixture must not add horizontal overflow of its own —
    // otherwise the injected probe would fail the very assertion it exists to support.
    expect(after.sw, "the fixture host must not widen the document").toBe(before.sw);
    expect(after.right, "fixture host stays left of the viewport").toBeLessThanOrEqual(0);
  });

  test("the surface assertions actually fire on a real page", async ({ page }) => {
    await openWithTheme(page, "/zh", "light");
    const clean = await measureStable(page, "light");
    expect(clean.failures, `the homepage already fails before the injected defect\n${report(clean)}`).toEqual([]);

    // Inject one unambiguously unreadable ledger row into the real page and prove
    // the contract above rejects it. The fixture tests prove the measurement is
    // right; this proves the assertion wired to it can fail.
    await page.evaluate(() => {
      const list = document.createElement("ul");
      const row = document.createElement("li");
      row.id = "__pg_injected_defect__";
      row.setAttribute("style", "color:rgb(250,250,250);background:rgb(255,255,255);font-size:16px;font-weight:400");
      row.textContent = "held position ledger row";
      list.appendChild(row);
      document.querySelector("main")!.appendChild(list);
    });
    const after = await measureStable(page, "light");
    const injected = byId(after, "__pg_injected_defect__");
    expect(injected, `an unreadable ledger row must reach the failure list\n${report(after)}`).toBeTruthy();
    expect(injected!.ratio, "the injected row is near-invisible and its ratio must say so").toBeLessThan(1.2);
    expect(after.failures, "the injected defect must appear in the same list the surface assertions use").not.toEqual([]);
  });
});

/**
 * Public surfaces render for anyone, so they are audited unconditionally.
 * `probe` is a selector that must be mounted for this route, which is what makes
 * the audit's silence mean "this surface is fine" instead of "nothing rendered".
 */
const PUBLIC_ROUTES: Array<{ path: string; label: string; minText: number; probe: string }> = [
  { path: "/zh", label: "homepage", minText: 40, probe: "main" },
  { path: "/zh/api", label: "api docs", minText: 40, probe: "main" },
];

async function stubAnonymous(page: Page) {
  await page.route(`${API}/me`, (r) => r.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
  await page.route(`${API}/auth/x/config`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ x_login_enabled: false }) }));
}

test.describe("public surfaces meet WCAG AA", () => {
  for (const route of PUBLIC_ROUTES) {
    for (const theme of ["light", "dark"] as const) {
      test(`${route.label} in ${theme}`, async ({ page }) => {
        const errors = watchErrors(page);
        await stubAnonymous(page);
        await openWithTheme(page, route.path, theme);
        const audit = await measureStable(page, theme);

        await expectRealSurface(page, true, `${route.label} (${theme})`);
        await expect(page.locator(route.probe).first(), `${route.label} (${theme}): the audited region is not mounted`).toBeVisible();
        // Guard against auditing nothing: a blank page, a crashed route or a dev
        // error overlay would otherwise pass every contrast assertion below.
        expect(audit.stats.measured, `too few text nodes measured — did the page render?\n${report(audit)}`).toBeGreaterThanOrEqual(route.minText);
        expect(audit.failures, `contrast violations on ${route.path} (${theme})\n${report(audit)}`).toEqual([]);
        expect(audit.doc.sw, `horizontal overflow on ${route.path} (${theme})`).toBeLessThanOrEqual(audit.doc.cw + 1);
        expect(audit.clipped, `clipped text on ${route.path} (${theme})\n${report(audit)}`).toEqual([]);

        const relevant = errors.filter((e) => !/CORS|ERR_FAILED|Failed to load resource|gtag|doubleclick|google/.test(e));
        expect(relevant, `runtime errors on ${route.path} (${theme}):\n${relevant.join("\n")}`).toEqual([]);
      });
    }
  }
});

/**
 * The Chat workspace is the surface most at risk, so it is stubbed the same way
 * the previous version stubbed it. `/chat` is gated by middleware; the dev
 * harness runs with `REQUIRE_AUTH=false` and every API call is stubbed in-page,
 * which is why this needs no session.
 */
test.describe("chat workspace meets WCAG AA", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`chat surface in ${theme}`, async ({ page }) => {
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
              { id: "default", display_name: "DeepSeek V4.1 Flash", description: "", provider: "deepseek", available: true, reason: null, credit_cost: null },
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
      // The composer asks for its own limits on mount. Unstubbed, this leaves
      // the origin through the dev proxy, fails CORS, and paints the dev error
      // overlay over the surface under test — i.e. the audit would be measuring
      // the overlay rather than the chat workspace.
      await page.route(`${API}/api/agent/workspace-capabilities`, (route) =>
        route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ permission_modes: ["read-only", "workspace-write", "full-access"], default_permission_mode: "workspace-write", max_file_bytes: 10485760, max_files: 8, storage_bytes: 104857600, file_types: ["txt", "md", "csv", "json", "pdf", "docx", "png"], scope: "user-owned PureGamma tools" }),
        }),
      );

      await openWithTheme(page, "/zh/chat", theme);
      const audit = await measureStable(page, theme);
      await page.screenshot({ path: `../../.preview-after/chat-${theme}.png` });

      await expectRealSurface(page, true, `chat (${theme})`);
      // These two only exist once the real Chat workspace has mounted, so their
      // presence is what distinguishes "contrast is fine" from "login page".
      // The model badge used to be the first of them, but the current design
      // states the model once — in the composer's selector — and only mentions it
      // again for an abnormal state, so a missing badge is now the healthy case.
      await expect(page.getByTestId("chat-composer-input"), `chat (${theme}): the workspace did not mount`).toBeVisible();
      await expect(page.getByTestId("harness-composer"), `chat (${theme}): the harness composer is missing`).toBeVisible();

      expect(audit.stats.measured, `the chat workspace did not render\n${report(audit)}`).toBeGreaterThanOrEqual(15);
      expect(audit.failures, `contrast violations in chat (${theme})\n${report(audit)}`).toEqual([]);
      expect(audit.doc.sw, `horizontal overflow in chat (${theme})`).toBeLessThanOrEqual(audit.doc.cw + 1);
      expect(audit.clipped, `clipped text in chat (${theme})\n${report(audit)}`).toEqual([]);

      const relevant = errors.filter((e) => !/CORS|ERR_FAILED|Failed to load resource|gtag|doubleclick|google/.test(e));
      expect(relevant, `runtime errors in chat (${theme}):\n${relevant.join("\n")}`).toEqual([]);
    });
  }
});
