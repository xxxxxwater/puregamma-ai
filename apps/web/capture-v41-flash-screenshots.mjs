// Final delivery screenshots for the DeepSeek V4.1 Flash frontend upgrade.
//
// Usage: start the preview server, then
//   node capture-v41-flash-screenshots.mjs
// Env: PREVIEW_BASE (default http://127.0.0.1:3100), SHOT_DIR
//       (default ../../.preview-after)
//
// The API docs page reads the Gateway catalog in the browser and production
// CORS only allows the app.puregamma.ai origin, so a captured copy of the real
// response is replayed for that page. The homepages are server-rendered from
// the live API and are captured unmocked.
import { chromium, devices } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";

const BASE = process.env.PREVIEW_BASE || "http://127.0.0.1:3100";
const OUT = process.env.SHOT_DIR || "../../.preview-after";
mkdirSync(OUT, { recursive: true });

const CATALOG = JSON.parse(
  readFileSync(new URL("../../tests/e2e/playwright/fixtures/gateway-catalog.json", import.meta.url), "utf8"),
);

const browser = await chromium.launch();

async function page(options = {}, { stubCatalog = true } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, ...options });
  const p = await context.newPage();
  if (stubCatalog) {
    await p.route("**/gateway/catalog*", (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(CATALOG) }),
    );
  }
  return { context, page: p };
}

// 1 + 2 — Chinese homepage and its preview card (live API, unmocked).
{
  const { context, page: p } = await page({}, { stubCatalog: false });
  await p.goto(`${BASE}/zh`, { waitUntil: "domcontentloaded" });
  await p.screenshot({ path: `${OUT}/01-home-zh-desktop.png` });
  await p.getByTestId("model-upgrade-preview").screenshot({ path: `${OUT}/02-home-zh-preview-card.png` });
  await context.close();
}

// 3 — English homepage (live API, unmocked).
{
  const { context, page: p } = await page({}, { stubCatalog: false });
  await p.goto(`${BASE}/en`, { waitUntil: "domcontentloaded" });
  await p.screenshot({ path: `${OUT}/03-home-en-desktop.png` });
  await p.getByTestId("model-upgrade-preview").screenshot({ path: `${OUT}/04-home-en-preview-card.png` });
  await context.close();
}

// 5 — API docs: full catalog table (Chinese).
{
  const { context, page: p } = await page();
  await p.goto(`${BASE}/zh/api`, { waitUntil: "domcontentloaded" });
  await p.getByTestId("catalog-model-table").waitFor({ state: "visible" });
  await p.getByTestId("catalog-model-table").scrollIntoViewIfNeeded();
  await p.screenshot({ path: `${OUT}/05-api-docs-zh-catalog.png` });
  await context.close();
}

// 6 — Gateway console shell (Chinese).
{
  const { context, page: p } = await page();
  await p.goto(`${BASE}/zh/gateway`, { waitUntil: "domcontentloaded" });
  await p.screenshot({ path: `${OUT}/06-gateway-zh.png` });
  await context.close();
}

// 7 — Agent Chat: model badge under the composer (Chinese, anonymous shell).
{
  const { context, page: p } = await page();
  await p.goto(`${BASE}/zh/chat`, { waitUntil: "domcontentloaded" });
  await p.screenshot({ path: `${OUT}/07-chat-zh-model-badge.png` });
  await context.close();
}

// 8 + 9 — Mobile homepage at 393px, both locales.
for (const locale of ["zh", "en"]) {
  const { context, page: p } = await page({ ...devices["Pixel 5"] }, { stubCatalog: false });
  await p.goto(`${BASE}/${locale}`, { waitUntil: "domcontentloaded" });
  await p.screenshot({ path: `${OUT}/08-mobile-${locale}-home.png` });
  await p.getByTestId("model-upgrade-preview").screenshot({ path: `${OUT}/09-mobile-${locale}-preview-card.png` });
  await context.close();
}

// 10 — Dark and light theme on the preview card.
// The theme is a `data-theme` attribute backed by localStorage, not a
// prefers-color-scheme media query, so it has to be seeded before navigation.
for (const theme of ["dark", "light"]) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript((value) => {
    window.localStorage.setItem("pg_theme", value);
  }, theme);
  const p = await context.newPage();
  await p.goto(`${BASE}/zh`, { waitUntil: "domcontentloaded" });
  // `data-theme` is applied by AppearanceControls after hydration, so the shot
  // is only trustworthy once it agrees with the seeded preference.
  await p.waitForFunction((value) => document.documentElement.dataset.theme === value, theme, { timeout: 15000 });
  const preview = p.getByTestId("model-upgrade-preview");
  await preview.waitFor({ state: "visible" });
  await preview.screenshot({ path: `${OUT}/10-preview-card-${theme}.png` });
  await context.close();
}

// 11 — Brand check: the sidebar wordmark and the dashboard title must read
// "PureGamma AI", not any other product name.
for (const locale of ["zh", "en"]) {
  const { context, page: p } = await page({}, { stubCatalog: false });
  await p.goto(`${BASE}/${locale}`, { waitUntil: "domcontentloaded" });
  const brand = await p.locator("aside a").first().innerText();
  const title = await p.title();
  const hasOldBrand = (await p.locator("body").innerText()).includes("PureGamma Intelligence");
  console.log(`${locale}: sidebar="${brand.replace(/\s+/g, " ")}" title="${title}" oldBrandPresent=${hasOldBrand}`);
  await p.locator("aside").first().screenshot({ path: `${OUT}/11-brand-${locale}-sidebar.png` });
  await context.close();
}

for (const locale of ["zh", "en"]) {
  const { context, page: p } = await page({}, { stubCatalog: false });
  await p.goto(`${BASE}/${locale}/dashboard`, { waitUntil: "domcontentloaded" });
  console.log(`${locale} dashboard title: "${await p.title()}"`);
  await context.close();
}

await browser.close();
console.log(`screenshots written to ${OUT}`);
