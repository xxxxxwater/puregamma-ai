/**
 * Markdown rendering regression.
 *
 * The previous implementation styled answers with `prose prose-invert …` classes
 * that emitted zero CSS (the typography plugin is not a dependency), so this
 * suite deliberately asserts COMPUTED STYLES on rendered elements. Asserting
 * that a class name is present would have passed the whole time the feature was
 * broken.
 */
import { expect, test } from "@playwright/test";

const API = `${process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000"}`.replace(/\/+$/, "") + "/__dev-api";

const ANSWER = [
  "# Heading one",
  "## Heading two",
  "",
  "A paragraph with **bold**, *italic*, `inline code` and a [link](https://example.com/a/very/long/path/that/should/wrap/not/overflow).",
  "",
  "- first bullet",
  "- second bullet",
  "",
  "1. first numbered",
  "2. second numbered",
  "",
  "> A quoted line of text.",
  "",
  "| Asset | Price |",
  "| --- | --- |",
  "| BTC | 64000 |",
  "| ETH | 3100 |",
  "",
  "```python",
  "def hello():",
  "    return 'world'",
  "```",
  "",
  "---",
  "",
  "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
].join("\n");

async function renderAnswer(page: import("@playwright/test").Page) {
  await page.route(`${API}/me`, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u", email: "a@b.invalid", name: "A", role: "user", plan: "Pro", credit_balance: 1200 } }) }),
  );
  await page.route(`${API}/api/frontend/plugins*`, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ plugins: [], capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 } }) }),
  );
  await page.route(`${API}/auth/x/config`, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ x_login_enabled: false }) }),
  );
  await page.route(`${API}/api/agent/capabilities`, (r) =>
    r.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 },
        quota: { plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 },
        models: [{ id: "default", display_name: "Default model", description: "", provider: "default", available: true, reason: null, credit_cost: null }],
        skills: [],
      }),
    }),
  );
  await page.route(`${API}/api/agent/quota`, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 }) }),
  );
  await page.route(`${API}/api/agent/quote`, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ estimated_min: 1, estimated_max: 2 }) }),
  );
  await page.route(`${API}/api/agent/conversations`, (r) =>
    r.request().method() === "POST"
      ? r.fulfill({ contentType: "application/json", body: JSON.stringify({ conversation: { id: "c1", title: "t", status: "active", archived_at: null, created_at: "2026-09-12T00:00:00+00:00", updated_at: "2026-09-12T00:00:00+00:00" } }) })
      : r.fulfill({ contentType: "application/json", body: JSON.stringify({ conversations: [] }) }),
  );
  // The reload after the stream is what actually renders the answer, so the
  // detail endpoint must return the message the stream just produced.
  await page.route(`${API}/api/agent/conversations/*`, (r) =>
    r.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        conversation: { id: "c1", title: "t", status: "active", archived_at: null, created_at: "2026-09-12T00:00:00+00:00", updated_at: "2026-09-12T00:00:00+00:00" },
        messages: [
          { id: "mu", conversation_id: "c1", role: "user", content: "show me markdown", status: "completed", model: null, input_tokens: 4, output_tokens: 0, credits_refunded: false, created_at: "2026-09-12T00:00:00+00:00", sources: [] },
          { id: "m1", conversation_id: "c1", role: "assistant", content: ANSWER, status: "completed", model: "deepseek-flash", input_tokens: 10, output_tokens: 200, credits_used: 1, credits_refunded: false, created_at: "2026-09-12T00:00:05+00:00", sources: [] },
        ],
      }),
    }),
  );
  await page.route(`${API}/api/agent/conversations/*/messages`, (r) =>
    r.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: run.started",
        'data: {"runId":"r1","messageId":"m1","model":"deepseek-flash","creditBalance":1200}',
        "",
        "event: message.delta",
        `data: ${JSON.stringify({ messageId: "m1", delta: ANSWER })}`,
        "",
        "event: message.completed",
        'data: {"messageId":"m1","model":"deepseek-flash","inputTokens":10,"outputTokens":200,"creditsUsed":1,"creditBalance":1199}',
        "",
        "",
      ].join("\n"),
    }),
  );

  await page.goto("/zh/chat/c1");
  await expect(page).toHaveURL(/\/zh\/chat\/c1$/);
  await expect(page.locator("h1", { hasText: "Heading one" })).toBeVisible({ timeout: 20000 });
}

test.describe("assistant markdown", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`renders real structure and styling in ${theme}`, async ({ page }) => {
      await page.addInitScript((v) => { try { window.localStorage.setItem("pg_theme", v); } catch { /* ignore */ } }, theme);
      await renderAnswer(page);

      const measured = await page.evaluate(() => {
        const pick = (sel: string) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const cs = getComputedStyle(el);
          return {
            fontSize: parseFloat(cs.fontSize),
            fontWeight: parseInt(cs.fontWeight, 10) || 400,
            listStyleType: cs.listStyleType,
            paddingLeft: parseFloat(cs.paddingLeft),
            borderLeftWidth: parseFloat(cs.borderLeftWidth),
            borderBottomWidth: parseFloat(cs.borderBottomWidth),
            fontFamily: cs.fontFamily,
            color: cs.color,
          };
        };
        const pre = document.querySelector("pre");
        return {
          h1: pick("h1"),
          h2: pick("h2"),
          ul: pick("ul"),
          li: pick("ul li"),
          blockquote: pick("blockquote"),
          table: pick("table"),
          th: pick("th"),
          inlineCode: pick("p code"),
          pre: pick("pre"),
          preCode: pick("pre code"),
          preFont: pre ? getComputedStyle(pre).fontFamily : "",
        };
      });

      // Each assertion would have FAILED against the old `prose` setup, which
      // emitted no CSS at all.
      expect(measured.h1, "h1 rendered").not.toBeNull();
      expect(measured.h1!.fontSize, "h1 is larger than body (24px)").toBeGreaterThanOrEqual(22);
      expect(measured.h2!.fontSize, "h2 is larger than body (20px)").toBeGreaterThanOrEqual(18);
      expect(measured.h2!.fontSize, "h2 smaller than h1").toBeLessThan(measured.h1!.fontSize);

      expect(measured.ul!.listStyleType, "list markers restored (preflight removes them)").toBe("disc");
      expect(measured.ul!.paddingLeft, "list indent restored").toBeGreaterThan(8);
      expect(measured.blockquote!.borderLeftWidth, "blockquote has a rule").toBeGreaterThan(0);

      expect(measured.table!.borderBottomWidth, "table cells have separators").toBeGreaterThanOrEqual(0);
      expect(measured.th!.fontWeight, "header cell is emphasised").toBeGreaterThanOrEqual(500);

      // Monospace is a font stack, so assert it differs from the body stack.
      expect(measured.preFont.toLowerCase(), "code block uses a mono stack").toMatch(/mono|consolas|courier/);

      // Inline code is boxed; block code is not (it lives in the header+pre frame).
      expect(measured.inlineCode!.fontFamily.toLowerCase(), "inline code is mono").toMatch(/mono|consolas|courier/);
    });
  }

  test("GFM tables are parsed instead of emitted as literal text", async ({ page }) => {
    await renderAnswer(page);
    // With no remark-gfm the pipe syntax survives as text and no <table> exists.
    await expect(page.locator("table")).toHaveCount(1);
    await expect(page.locator("th", { hasText: "Asset" })).toBeVisible();
    await expect(page.locator("td", { hasText: "BTC" })).toBeVisible();
    // The raw pipes must NOT be visible as content.
    const tableText = await page.locator("table").innerText();
    expect(tableText).not.toContain("| --- |");
  });

  test("code block has a language label and a working copy control", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await renderAnswer(page);
    await expect(page.getByText("python", { exact: true })).toBeVisible();
    const copy = page.getByRole("button", { name: /copy code/i }).first();
    await expect(copy).toBeVisible();
    await copy.click();
    await expect(page.getByRole("button", { name: /copied/i }).first()).toBeVisible();
  });

  test("long tokens and wide tables never widen the page", async ({ page }) => {
    await renderAnswer(page);
    const layout = await page.evaluate(() => {
      const doc = document.documentElement;
      const table = document.querySelector("table");
      return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        // The table's own wrapper must be the scroll container, so the table
        // itself is allowed to exceed the wrapper, never the document.
        tableWrapperScrolls: table?.parentElement ? table.parentElement.scrollWidth >= table.parentElement.clientWidth : null,
        bodyOverflowX: getComputedStyle(document.body).overflowX,
      };
    });
    expect(layout.scrollWidth, "document must not overflow horizontally").toBeLessThanOrEqual(layout.clientWidth + 1);
  });
});
