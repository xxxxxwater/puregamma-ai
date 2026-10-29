/**
 * Entry to the DSH Session front door (multi-tenant session broker).
 *
 * The link is a build-time flag: NEXT_PUBLIC_DSH_SESSIONS_URL. Run this spec
 * twice: without the variable (the default, production today) the chat
 * workspace must show no entry; with it set, the entry points exactly there,
 * opens in a new browsing context without an opener or referrer, and does not
 * push the composer below the fold. The app keeps no Session state for it.
 */
import { expect, test, type Page } from "@playwright/test";

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";
const configured = process.env.NEXT_PUBLIC_DSH_SESSIONS_URL?.trim() || "";

async function stub(page: Page) {
  await page.route(`${API}/**`, (r) => r.fulfill({ json: {} }));
  await page.route(`${API}/me`, (r) => r.fulfill({ json: { user: { id: "u", email: "a@b.invalid", name: "A", role: "user", plan: "Pro", credit_balance: 1200 } } }));
  await page.route(`${API}/api/frontend/plugins*`, (r) => r.fulfill({ json: { plugins: [], capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 } } }));
  await page.route(`${API}/auth/x/config`, (r) => r.fulfill({ json: { x_login_enabled: false } }));
  await page.route(`${API}/api/agent/capabilities`, (r) => r.fulfill({ json: {
    capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 },
    quota: { plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 },
    models: [{ id: "default", display_name: "Default model", description: "", provider: "default", available: true, reason: null, credit_cost: null }],
    skills: [] } }));
  await page.route(`${API}/api/agent/quota`, (r) => r.fulfill({ json: { plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 } }));
  await page.route(`${API}/api/agent/conversations`, (r) => r.fulfill({ json: { conversations: [] } }));
  await page.route(`${API}/api/agent/workspace-capabilities`, (r) => r.fulfill({ json: { max_file_bytes: 10485760, max_files: 8, file_types: ["txt", "png"] } }));
}

test("chat shows no Harness sessions entry unless the build enables it", async ({ page }) => {
  test.skip(Boolean(configured), "flag set for this run; see the enabled test");
  await stub(page);
  await page.goto("/zh/chat");
  // The page has rendered its own content before the absence is asserted.
  await expect(page.getByRole("heading", { name: "与 Agent 共同推理。" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "向 PureGamma 提问…" })).toBeVisible();
  await expect(page.getByTestId("harness-sessions-link")).toHaveCount(0);
  await expect(page.getByText("打开 Harness 会话")).toHaveCount(0);
});

test("with NEXT_PUBLIC_DSH_SESSIONS_URL the chat header links to the session broker", async ({ page }) => {
  test.skip(!configured, "set NEXT_PUBLIC_DSH_SESSIONS_URL to run");
  await stub(page);
  for (const [locale, label] of [["zh", "打开 Harness 会话"], ["en", "Open Harness sessions"]] as const) {
    await page.goto(`/${locale}/chat`);
    const link = page.getByTestId("harness-sessions-link");
    await expect(link).toBeVisible();
    await expect(link).toHaveText(label);
    await expect(link).toHaveAttribute("href", new URL(configured).href);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  const composer = page.getByRole("textbox", { name: "Ask PureGamma…" });
  await expect(composer).toBeVisible();
  const box = await composer.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
});
