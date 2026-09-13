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

test.describe("chat workspace", () => {
  test("both chat routes use the same content width", async ({ page }) => {
    await stub(page);
    const measure = async (path: string) => {
      await page.goto(path);
      await expect(page.locator("textarea")).toBeVisible({ timeout: 15000 });
      return page.evaluate(() => {
        const shell = document.querySelector('[class*="max-w-[1180px]"]') as HTMLElement | null;
        const column = document.querySelector(".max-w-3xl") as HTMLElement | null;
        return {
          shell: shell ? Math.round(shell.getBoundingClientRect().width) : null,
          column: column ? Math.round(column.getBoundingClientRect().width) : null,
        };
      });
    };
    const fresh = await measure("/zh/chat");
    const detail = await measure("/zh/chat/c1");
    expect(fresh.shell, "the empty route must be inside the shared width contract").not.toBeNull();
    expect(detail.shell, "the detail route must be inside the same contract").not.toBeNull();
    expect(detail.shell, "same shell width on both routes").toBe(fresh.shell);
    expect(detail.column, "same text column on both routes").toBe(fresh.column);
  });

  test("a long answer is readable and scrollable, not clipped", async ({ page }) => {
    await stub(page);
    await page.goto("/zh/chat/c1");
    await expect(page.locator("table")).toBeVisible({ timeout: 15000 });

    const result = await page.evaluate(() => {
      const doc = document.documentElement;
      const wrapper = document.querySelector("table")?.parentElement as HTMLElement | null;
      return {
        docOverflow: doc.scrollWidth - doc.clientWidth,
        // The table must be reachable by scrolling its own wrapper.
        wrapperScrolls: wrapper ? wrapper.scrollWidth > wrapper.clientWidth : false,
        wrapperOverflowX: wrapper ? getComputedStyle(wrapper).overflowX : "",
      };
    });
    // Not merely "the page does not overflow" — that was true while content was
    // being cut off. The table must be inside a horizontally scrollable box.
    expect(result.docOverflow, "the document itself must not overflow").toBeLessThanOrEqual(1);
    expect(["auto", "scroll"], `table wrapper overflowX was "${result.wrapperOverflowX}"`).toContain(result.wrapperOverflowX);
    expect(result.wrapperScrolls, "a wide table must be scrollable inside its container").toBe(true);
  });

  test("the composer is inside the initial viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await stub(page);
    await page.goto("/zh/chat");
    await expect(page.locator("textarea")).toBeVisible({ timeout: 15000 });
    const box = await page.locator("textarea").boundingBox();
    expect(box, "composer must be measurable").not.toBeNull();
    expect(box!.y + box!.height, "the primary control must not sit below the fold").toBeLessThanOrEqual(900);
  });

  test("history is reachable on a phone through the drawer", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stub(page);
    await page.goto("/zh/chat/c1");
    await expect(page.locator("textarea")).toBeVisible({ timeout: 15000 });

    const trigger = page.getByTestId("chat-history-trigger");
    await expect(trigger, "a phone needs a way into the conversation list").toBeVisible();

    const panel = page.getByRole("complementary", { name: /历史对话|Conversation history/ });
    await expect(panel, "drawer starts closed").toBeHidden();

    await trigger.click();
    await expect(panel).toBeVisible();
    await expect(page.getByText("长内容复核")).toBeVisible();

    // Escape closes it and focus returns to the trigger.
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(trigger, "focus must return to the trigger").toBeFocused();
  });

  test("the drawer does not hide the transcript with no way back", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stub(page);
    await page.goto("/zh/chat/c1");
    await expect(page.locator("textarea")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("chat-history-trigger").click();
    // A backdrop button exists so the drawer can be dismissed by pointing at the
    // content behind it, and the body cannot scroll underneath.
    const backdrop = page.getByRole("button", { name: /关闭历史对话|Close conversation history/ });
    expect(await backdrop.count(), "drawer needs a dismiss affordance").toBeGreaterThan(0);
    const bodyOverflow = await page.evaluate(() => getComputedStyle(document.body).overflow);
    expect(bodyOverflow, "background scroll must be locked while the drawer is open").toBe("hidden");
  });
});
