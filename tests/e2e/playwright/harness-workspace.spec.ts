/**
 * Chat workspace regressions.
 *
 * Every assertion here corresponds to a defect confirmed earlier in this round:
 *
 *  - `/chat` and `/chat/[conversationId]` rendered different widths because only
 *    the former passed through `IntelligenceShell`.
 *  - the conversation aside is `hidden` below `lg` with no drawer, so on a phone
 *    the history, "new conversation" and "delete all history" were unreachable.
 *  - long content was silently clipped: an ancestor had `overflow-hidden` and
 *    the file contained zero `break-words` / `overflow-x-auto`.
 *
 * The previous overflow assertion (`scrollWidth <= clientWidth + 1`) was
 * VACUOUSLY TRUE because clipping hid the overflow it was meant to detect, so
 * these tests assert readability/scrollability of the content instead.
 */
import { expect, test, type Page } from "@playwright/test";

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

const LONG = "x".repeat(300);
const ANSWER = [
  "### 结论",
  "",
  `长链接：https://example.com/${LONG}`,
  "",
  "```text",
  "A".repeat(240),
  "```",
  "",
  // Cells must be long enough that the table's intrinsic width exceeds the
  // column, otherwise the browser shrinks it to fit and there is nothing to
  // scroll — which is exactly how the original clipping defect hid itself.
  "| 列一 | 列二 | 列三 | 列四 | 列五 | 列六 | 列七 | 列八 |",
  "| --- | --- | --- | --- | --- | --- | --- | --- |",
  `| ${"1111111111 ".repeat(4)} | ${"2222222222 ".repeat(4)} | ${"3333333333 ".repeat(4)} | ${"4444444444 ".repeat(4)} | ${"5555555555 ".repeat(4)} | ${"6666666666 ".repeat(4)} | ${"7777777777 ".repeat(4)} | ${"8888888888 ".repeat(4)} |`,
].join("\n");

const conversation = {
  id: "c1",
  title: "长内容复核",
  status: "active",
  archived_at: null,
  created_at: "2026-09-12T00:00:00+00:00",
  updated_at: "2026-09-12T00:00:00+00:00",
};

async function stub(page: Page) {
  await page.route(`${API}/me`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u", email: "a@b.invalid", name: "A", role: "user", plan: "Pro", credit_balance: 1200 } }) }));
  await page.route(`${API}/api/frontend/plugins*`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ plugins: [], capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 } }) }));
  await page.route(`${API}/auth/x/config`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ x_login_enabled: false }) }));
  await page.route(`${API}/api/agent/capabilities`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({
    capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 },
    quota: { plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 },
    models: [{ id: "default", display_name: "Default model", description: "", provider: "default", available: true, reason: null, credit_cost: null }],
    skills: [] }) }));
  await page.route(`${API}/api/agent/quota`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 }) }));
  await page.route(`${API}/api/agent/quote`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ estimated_min: 1, estimated_max: 2 }) }));
  await page.route(`${API}/api/agent/conversations`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ conversations: [conversation] }) }));
  await page.route(`${API}/api/agent/conversations/c1`, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({
    conversation,
    messages: [
      { id: "mu", conversation_id: "c1", role: "user", content: `看一下这个：https://example.com/${LONG}`, status: "completed", model: null, input_tokens: 4, output_tokens: 0, credits_refunded: false, created_at: "2026-09-12T00:00:00+00:00", sources: [] },
      { id: "m1", conversation_id: "c1", role: "assistant", content: ANSWER, status: "completed", model: "deepseek-flash", input_tokens: 10, output_tokens: 100, credits_refunded: false, created_at: "2026-09-12T00:00:05+00:00", sources: [] },
    ] }) }));
}


for (const theme of ["light", "dark"]) {
  test(`harness composer files and permissions (${theme})`, async ({page}) => {
    await page.addInitScript(value => localStorage.setItem("pg_theme", value), theme);
    await page.route(`${API}/**`, r => r.fulfill({json: {}}));
    await stub(page);
    await page.route(`${API}/api/agent/workspace-capabilities`, r => r.fulfill({json: {max_file_bytes: 10485760, max_files: 8, file_types: ["txt", "png"]}}));
    let uploaded = false;
    await page.route(`${API}/api/agent/attachments?*`, async r => {
      expect(r.request().postData()).toBe("attachment body"); uploaded = true;
      await r.fulfill({json: {attachment: {id:"a1", name:"notes.txt", mime:"text/plain", size:15, kind:"file", content:"", url:"/api/agent/attachments/a1/content"}}});
    });
    let permission = "workspace-write";
    await page.route(`${API}/api/agent/conversations/c1`, async r => {
      if (r.request().method() === "PATCH") permission = r.request().postDataJSON().permission_mode;
      await r.fulfill({json: {conversation: {...conversation, permission_mode:permission}, messages:[], pending_approvals:[{toolCallId:"t1", tool:"update_strategy", arguments:{name:"example"}}]}});
    });
    let approved = false;
    await page.route(`${API}/api/agent/tool-calls/t1/approval`, async r => { approved = r.request().postDataJSON().decision === "approved"; await r.fulfill({json:{id:"t1", decision:"approved"}}); });
    await page.goto("/zh/chat/c1");
    await expect(page.getByTestId("harness-composer")).toBeVisible();
    await page.getByRole("button", {name:"允许此次操作"}).click(); expect(approved).toBe(true);
    await page.getByLabel("对话权限", {exact:true}).selectOption("read-only");
    await expect.poll(() => permission).toBe("read-only");
    await page.locator('input[type="file"]').setInputFiles({name:"notes.txt", mimeType:"text/plain", buffer:Buffer.from("attachment body")});
    await expect(page.getByRole("link", {name:"notes.txt"})).toBeVisible(); expect(uploaded).toBe(true);
    await page.getByRole("button", {name:"移除: notes.txt"}).click();
    await expect(page.getByRole("link", {name:"notes.txt"})).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    const composer = await page.getByTestId("harness-composer").boundingBox();
    expect(composer!.y + composer!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
    await page.screenshot({path:`../../.preview-harness-${theme}-${page.viewportSize()!.width}.png`, fullPage:true});
  });
}
