import { expect, test, type Page } from "@playwright/test";
import catalogFixture from "./fixtures/gateway-catalog.json";

/**
 * DeepSeek V4.1 Flash frontend regression.
 *
 * The homepage reads the deployment catalog server-side, so the homepage specs
 * run against the live API. The API docs page reads the same catalog in the
 * browser, where production CORS only allows the app.puregamma.ai origin, so
 * those specs replay a captured copy of the real response
 * (`fixtures/gateway-catalog.json`, regenerate with the capture script noted in
 * the delivery report). The signed-in Agent Chat view cannot be reached without
 * an account, so its responses are mocked with payloads copied from the real
 * serializers in `apps/api/routers/agent.py` and
 * `apps/api/services/agent_service.py`.
 *
 * A passing mock test proves the UI handles the upgraded model payload; it is
 * NOT evidence that the model answered. Live end-to-end runs are tracked
 * separately in the delivery report.
 */

const FLASH = "deepseek-flash";
const FLASH_DISPLAY = "DeepSeek V4.1 Flash";

/** Serve the captured live catalog to browser-side callers. */
async function stubCatalog(page: Page) {
  await page.route("**/gateway/catalog*", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(catalogFixture) }),
  );
}

const USER = {
  user: {
    id: "u-model-upgrade",
    email: "model-upgrade@example.invalid",
    name: "Model Upgrade Fixture",
    role: "user",
    plan: "Pro",
    credit_balance: 1200,
    auth_provider: "email",
  },
};

const CAPABILITIES = {
  capabilities: {
    plan: "Pro",
    allowed_data_sources: ["all"],
    allowed_skills: ["all"],
    max_attachments: 5,
  },
  quota: { plan: "Pro", used: 3, limit: 200, remaining: 197, concurrent_limit: 2, running: 0, credit_balance: 1200 },
  models: [
    { id: "default", display_name: "Default model", description: "Uses the existing Agent default configuration.", provider: "default", available: true, reason: null, credit_cost: null },
    { id: "gpt-5.6-luna", display_name: "GPT-5.6 Luna", description: "High-quality deep market research for selective use.", provider: "openai", available: false, reason: "plan_required", credit_cost: null },
  ],
  skills: [],
};

const CONVERSATION = {
  id: "c-model-upgrade",
  title: "Model upgrade regression",
  status: "active",
  archived_at: null,
  created_at: "2026-09-11T08:00:00+00:00",
  updated_at: "2026-09-11T08:00:00+00:00",
};

/** An SSE body shaped exactly like `stream_run` emits it. */
const STREAM_BODY = [
  "event: run.started",
  `data: {"runId":"r1","messageId":"m-assistant","model":"${FLASH}","creditBalance":1190}`,
  "",
  "event: plan.ready",
  'data: {"intent":"market_research","assets":["BTC"],"evidenceRequirements":["quote"],"autoSelectedSkills":true,"clarificationRecommended":false}',
  "",
  "event: tool.started",
  'data: {"toolCallId":"t1","tool":"market_snapshot"}',
  "",
  "event: tool.completed",
  'data: {"toolCallId":"t1","tool":"market_snapshot","data":{"status":"ok"}}',
  "",
  "event: message.delta",
  'data: {"messageId":"m-assistant","delta":"BTC is trading "}',
  "",
  "event: message.delta",
  'data: {"messageId":"m-assistant","delta":"in its current range."}',
  "",
  "event: message.completed",
  `data: {"messageId":"m-assistant","model":"${FLASH}","inputTokens":120,"outputTokens":9,"creditsUsed":10,"creditBalance":1190,"nextActions":["set_watch"]}`,
  "",
  "",
].join("\n");

async function stubApi(page: Page, options: { assistantId?: string; assistantContent?: string; creditsRefunded?: boolean } = {}) {
  const assistantId = options.assistantId ?? "m-assistant";
  const assistantContent = options.assistantContent ?? "BTC is trading in its current range.";
  const creditsRefunded = options.creditsRefunded ?? false;
  await page.route("**/me", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(USER) }));
  await page.route("**/api/agent/capabilities", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(CAPABILITIES) }));
  await page.route("**/api/agent/quota", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(CAPABILITIES.quota) }),
  );
  await page.route("**/api/agent/conversations", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ contentType: "application/json", body: JSON.stringify({ conversation: CONVERSATION }) })
      : route.fulfill({ contentType: "application/json", body: JSON.stringify({ conversations: [] }) }),
  );
  await page.route("**/api/agent/conversations/**", (route) => {
    if (route.request().method() === "POST") return route.continue();
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        conversation: CONVERSATION,
        messages: [
          {
            id: "m-user",
            conversation_id: CONVERSATION.id,
            role: "user",
            content: "BTC market now",
            status: "completed",
            model: null,
            input_tokens: 4,
            output_tokens: 0,
            created_at: "2026-09-11T08:00:00+00:00",
            sources: [],
          },
          {
            id: assistantId,
            conversation_id: CONVERSATION.id,
            role: "assistant",
            content: assistantContent,
            status: "completed",
            model: FLASH,
            input_tokens: 120,
            output_tokens: 9,
            credits_used: 10,
            // Mirrors `serialize_message`: the stored settlement for this run.
            credits_refunded: creditsRefunded,
            created_at: "2026-09-11T08:00:05+00:00",
            sources: [],
          },
        ],
      }),
    });
  });
  await page.route("**/api/agent/quote", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ estimated_min: 8, estimated_max: 12 }) }),
  );
  await page.route("**/api/agent/conversations/*/messages", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: STREAM_BODY }),
  );
}

test.describe("homepage DeepSeek V4.1 Flash announcement", () => {
  test("Chinese homepage announces the model with one primary action", async ({ page }) => {
    await page.goto("/zh");
    const announcement = page.getByTestId("model-announcement");
    await expect(announcement).toBeVisible();
    await expect(announcement).toContainText("现已支持 DeepSeek V4.1 Flash");

    const preview = page.getByTestId("model-upgrade-preview");
    await expect(preview).toBeVisible();
    await expect(preview.getByRole("heading", { name: FLASH_DISPLAY, exact: true })).toBeVisible();
    // Published state comes from the catalog, never from static copy.
    await expect(preview).toHaveAttribute("data-model-availability", "available");
    // One prominent action; the other surfaces are quiet secondary links.
    await expect(preview.getByRole("link", { name: /进入 Agent 对话/ })).toHaveAttribute("href", "/zh/chat");
    await expect(preview.getByRole("link", { name: /^API 中转站$/ })).toHaveAttribute("href", "/zh/gateway");
    await expect(preview.getByRole("link", { name: /查看 API 接入文档/ })).toHaveAttribute("href", "/zh/api");
    await expect(preview).toContainText("对话、报告与研究");
  });

  test("the homepage states the model once and collapses every technical field", async ({ page }) => {
    await page.goto("/zh");
    const preview = page.getByTestId("model-upgrade-preview");
    // Technical detail (request id, upstream id, pricing, raw curl) lives inside
    // a closed <details>, so it does not take over the primary display area.
    const technical = preview.getByTestId("model-upgrade-technical");
    await expect(technical).toBeVisible();
    await expect(technical).not.toHaveAttribute("open", "");
    expect(await technical.locator("dl").isVisible()).toBe(false);
    // The status label is accurate without a paragraph defending it.
    await expect(preview).toContainText("已接入");
    await expect(preview).not.toContainText("运行健康状态由中转站单独监控");
    // The model name appears exactly once outside the collapsed region.
    const visibleName = await preview.getByRole("heading", { name: FLASH_DISPLAY, exact: true }).count();
    expect(visibleName).toBe(1);
    // A collapsed <details> still keeps its content in the DOM, so assert on
    // the summary's own subtree rather than on the whole card's text.
    const summary = technical.locator("summary");
    await expect(summary).not.toContainText("运行健康状态由中转站单独监控");
    await expect(summary).not.toContainText("deepseek-flash");
    await expect(summary).not.toContainText("请求示例");
  });

  test("expanding the technical section reveals the request id and alias", async ({ page }) => {
    await page.goto("/zh");
    const technical = page.getByTestId("model-upgrade-preview").getByTestId("model-upgrade-technical");
    await technical.locator("summary").click();
    // Assert on the rendered attribute rather than reading `.open` immediately:
    // a click that lands before hydration would otherwise race the toggle.
    await expect(technical).toHaveAttribute("open", "");
    // Assertions are retried, so a toggle that lands a beat later still passes.
    await expect(technical).toContainText(FLASH);
    await expect(technical).toContainText("deepseek-v4-flash");
    // The request example is explicitly labelled as an example.
    await expect(technical).toContainText("仅为示例");
    // The health caveat belongs with the technical detail, not in the summary.
    await expect(technical).toContainText("目录状态不等于健康检查");
  });

  test("English homepage announces the model with one primary action", async ({ page }) => {
    await page.goto("/en");
    const announcement = page.getByTestId("model-announcement");
    await expect(announcement).toContainText("DeepSeek V4.1 Flash is now available");

    const preview = page.getByTestId("model-upgrade-preview");
    await expect(preview).toHaveAttribute("data-model-availability", "available");
    await expect(preview.getByRole("link", { name: /Open Agent Chat/ })).toHaveAttribute("href", "/en/chat");
    await expect(preview.getByRole("link", { name: /^API Gateway$/ })).toHaveAttribute("href", "/en/gateway");
    await expect(preview).toContainText("chat, reports and research");
    await expect(preview).toContainText("Available");
    // The health caveat is disclosed with the technical detail, not in the
    // card's summary: a collapsed <details> keeps its content in the DOM, so
    // this checks the summary subtree rather than the card's text.
    const technical = preview.getByTestId("model-upgrade-technical");
    const summary = technical.locator("summary");
    await expect(summary).not.toContainText("Catalog status is not a health check");
    await technical.locator("summary").click();
    await expect(technical).toHaveAttribute("open", "");
    await expect(technical).toContainText("Catalog status is not a health check");
  });

  test("a pending catalog renders a non-live state instead of a green badge", async ({ page }) => {
    await page.route("**/gateway/catalog*", (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          gateway_enabled: true,
          markup_bps: 3000,
          updated_at: "2026-09-11T00:00:00+00:00",
          models: [
            {
              id: FLASH,
              display_name: FLASH_DISPLAY,
              provider: "deepseek",
              provider_display_name: "DeepSeek",
              provider_model_id: FLASH,
              capabilities: { max_context_tokens: 1048576 },
              metadata: {},
              availability: "pending_approval",
              pricing: null,
            },
          ],
        }),
      }),
    );
    // The homepage catalog is fetched server-side (so it renders the live
    // deployment), while the docs page reads the same endpoint in the browser:
    // that is where the stub applies.
    await page.goto("/zh/api");
    const table = page.getByTestId("catalog-model-table");
    await expect(table).toContainText("待价格审批");
    await expect(table).not.toContainText("已上线");
  });
});

test.describe("API docs model catalog", () => {
  test.beforeEach(async ({ page }) => {
    await stubCatalog(page);
  });

  test("lists every catalog model including the compatibility alias and other vendors", async ({ page }) => {
    await page.goto("/zh/api");
    const table = page.getByTestId("catalog-model-table");
    await expect(table).toBeVisible();
    await expect(table).toContainText(FLASH);
    await expect(table).toContainText("DeepSeek V4.1 Flash");
    await expect(table).toContainText("deepseek-v4-flash");
    await expect(table).toContainText("kimi-k3-max");
    await expect(table).toContainText("glm-5.2");
    // Reviewed price, read from the catalog rather than hardcoded copy.
    await expect(table).toContainText("0.15151515");
    // Other vendors keep their own availability state; only Flash is live here.
    await expect(table).toContainText("待价格审批");
    await expect(table).toContainText("配置中");
  });

  test("selecting a catalog row switches the detail panel and code samples", async ({ page }) => {
    await page.goto("/zh/api");
    await page.getByTestId("catalog-model-table").getByRole("button", { name: "glm-5.2", exact: true }).click();
    await expect(page.getByRole("heading", { name: "GLM 5.2" }).first()).toBeVisible();
    await expect(page.locator("pre", { hasText: '"model": "glm-5.2"' }).first()).toBeVisible();
  });

  test("a model without a curated narrative still renders from the catalog", async ({ page }) => {
    await page.route("**/gateway/catalog*", (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          gateway_enabled: true,
          markup_bps: 3000,
          updated_at: "2026-09-11T00:00:00+00:00",
          models: [
            {
              id: "deepseek-flash",
              display_name: FLASH_DISPLAY,
              provider: "deepseek",
              provider_display_name: "DeepSeek",
              provider_model_id: FLASH,
              capabilities: { chat: true, stream: true, max_context_tokens: 1048576 },
              metadata: {},
              availability: "available",
              pricing: {
                currency: "USD",
                official: { input: { amount: "0.15151515", unit: "per_million_tokens" }, output: { amount: "0.60606061", unit: "per_million_tokens" } },
                final: { input: { amount: "0.1969697", unit: "per_million_tokens" }, output: { amount: "0.78787879", unit: "per_million_tokens" } },
                status: "active",
              },
            },
            {
              id: "vendor-model-uncurated",
              display_name: "Vendor Uncurated Model",
              provider: "vendor",
              provider_display_name: "Vendor Inc",
              provider_model_id: "vendor-upstream-id",
              capabilities: { chat: true },
              metadata: {},
              availability: "setup_required",
              pricing: null,
            },
          ],
        }),
      }),
    );
    await page.goto("/zh/api");
    const table = page.getByTestId("catalog-model-table");
    await expect(table).toContainText("vendor-model-uncurated");
    await expect(table).toContainText("Vendor Inc");
    // An uncurated model must not break the curated cards above it.
    await expect(page.getByRole("heading", { name: FLASH_DISPLAY }).first()).toBeVisible();
  });

  test("English docs page and quick start use the canonical request id", async ({ page }) => {
    await page.goto("/en/api");
    await expect(page.getByTestId("catalog-model-table")).toContainText(FLASH);
    await expect(page.locator("pre", { hasText: `"model": "${FLASH}"` }).first()).toBeVisible();
    // No upstream key may appear in a browser-visible sample.
    await expect(page.locator("body")).not.toContainText("sk-pg-1");
  });
});

test.describe("Agent Chat model label", () => {
  test.beforeEach(async ({ page }) => {
    await stubApi(page);
  });

  test("the default selection is shown as DeepSeek V4.1 Flash, not 'Default model'", async ({ page }) => {
    await page.goto("/zh/chat");
    // The Chat surface bounces a visitor it believes is signed out. Without
    // this guard a stub regression would silently turn every assertion below
    // into an assertion about the login page.
    await expect(page).toHaveURL(/\/zh\/chat$/);
    const select = page.locator("#agent-model");
    await expect(select).toBeVisible();
    // The hidden value stays the routing sentinel so the backend still routes.
    await expect(select).toHaveValue("default");
    await expect(select.locator("option[value='default']")).toHaveText(/DeepSeek V4\.1 Flash/);
    await expect(select.locator("option[value='default']")).toHaveText(/平台默认路由/);
    // Other vendors keep their own name and are not rewritten.
    await expect(select.locator("option[value='gpt-5.6-luna']")).toHaveText(/GPT-5\.6 Luna/);
    // The current model is stated exactly once. A normal state stays quiet, so
    // the abnormal-state notice must not be on the page.
    await expect(page.getByTestId("chat-model-badge")).toHaveCount(0);
  });

  test("English chat label is localized", async ({ page }) => {
    await page.goto("/en/chat");
    await expect(page).toHaveURL(/\/en\/chat$/);
    await expect(page.locator("#agent-model option[value='default']")).toHaveText(/DeepSeek V4\.1 Flash/);
    await expect(page.locator("#agent-model option[value='default']")).toHaveText(/platform default route/);
  });

  test("a stored answer from another model is not relabelled as Flash", async ({ page }) => {
    await page.goto("/zh/chat/c-model-upgrade");
    await expect(page).toHaveURL(/\/zh\/chat\/c-model-upgrade$/);
    // The fixture's assistant message is recorded as deepseek-flash.
    await expect(page.getByText(FLASH_DISPLAY, { exact: false }).first()).toBeVisible();
  });

  test("streaming a turn keeps the assistant answer renderable", async ({ page }) => {
    await page.goto("/zh/chat");
    await expect(page).toHaveURL(/\/zh\/chat$/);
    await page.locator("textarea").fill("BTC market now");
    await page.keyboard.press("Enter");
    await expect(page.getByText("BTC is trading in its current range.")).toBeVisible({ timeout: 15000 });
  });
});

/**
 * Billing copy must follow the backend's settlement record, not the error type.
 * `apps/api/services/agent_service.py` refunds a failed run but *settles* the
 * tokens already produced when the client disconnects, so the UI may only state
 * an outcome the backend actually reported (`AgentMessage.credits_refunded`).
 *
 * These tests register their own stubs instead of layering them over
 * `stubApi`: `page.unroute` removes every handler matching the pattern
 * (including the conversation-detail stub the reload depends on), which would
 * otherwise change what the test is actually exercising.
 */
test.describe("Agent Chat billing copy follows the settlement record", () => {
  test.beforeEach(async ({ page }) => {
    await stubApi(page);
  });

  test("a failed run reports the refund the backend issued", async ({ page }) => {
    await page.route("**/api/agent/conversations/*/messages", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "event: run.started",
          'data: {"runId":"r2","messageId":"m-failed","model":"deepseek-flash","creditBalance":1180}',
          "",
          "event: run.failed",
          'data: {"runId":"r2","messageId":"m-failed","code":"AGENT_MODEL_TIMEOUT","message":"The answer took too long to generate. Credits were refunded.","creditBalance":1190}',
          "",
          "",
        ].join("\n"),
      }),
    );
    await page.goto("/zh/chat");
    // Guard: a signed-out redirect would make these assertions meaningless.
    await expect(page).toHaveURL(/\/zh\/chat$/);
    await page.locator("textarea").fill("trigger a refunded failure");
    await page.keyboard.press("Enter");
    const billing = page.getByTestId("chat-error-billing");
    await expect(billing).toBeVisible({ timeout: 15000 });
    await expect(billing).toHaveAttribute("data-billing", "refunded");
    await expect(billing).toContainText("本次运行未扣除 Credits");
  });

  test("an interrupted stream does not promise a refund", async ({ page }) => {
    // A stream that dies after a delta and never completes: the client cannot
    // know the settlement, so the copy must stay neutral.
    await page.route("**/api/agent/conversations/*/messages", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "event: run.started",
          'data: {"runId":"r3","messageId":"m-cut","model":"deepseek-flash","creditBalance":1180}',
          "",
          "event: message.delta",
          'data: {"messageId":"m-cut","delta":"partial answer"}',
          "",
          "",
        ].join("\n"),
      }),
    );
    await page.goto("/zh/chat");
    // Guard: a signed-out redirect would make these assertions meaningless.
    await expect(page).toHaveURL(/\/zh\/chat$/);
    await page.locator("textarea").fill("interrupt me");
    await page.keyboard.press("Enter");
    const billing = page.getByTestId("chat-error-billing");
    await expect(billing).toBeVisible({ timeout: 15000 });
    await expect(billing).toHaveAttribute("data-billing", "unknown");
    await expect(billing).toContainText("费用状态请查看用量记录");
    await expect(billing).not.toContainText("未扣除");
  });

  test("a stream cut without an error event is still reported", async ({ page }) => {
    // A proxy can close the body cleanly mid-answer. The stream loop exits
    // normally, so the UI must detect the missing `message.completed` itself.
    await page.route("**/api/agent/conversations/*/messages", (route) =>
      route.fulfill({ status: 200, contentType: "text/event-stream", body: "event: run.started\ndata: {\"runId\":\"r5\",\"messageId\":\"m-silent\",\"model\":\"deepseek-flash\"}\n\n" }),
    );
    await page.goto("/zh/chat");
    // Guard: a signed-out redirect would make these assertions meaningless.
    await expect(page).toHaveURL(/\/zh\/chat$/);
    await page.locator("textarea").fill("cut me silently");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("chat-error")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("chat-error")).toContainText("中断");
    await expect(page.getByTestId("chat-error-billing")).toHaveAttribute("data-billing", "unknown");
  });

  test("an empty answer reports the recorded settlement instead of assuming it was free", async ({ page }) => {
    // This run completes with no text and the persisted message comes back with
    // a settled (not refunded) run, so `credits_refunded: false` is the record
    // the copy must follow.
    // The reload must see the same message the stream reported, with the
    // backend's settlement flag on it.
    await stubApi(page, { assistantId: "m-empty", assistantContent: "", creditsRefunded: false });
    await page.route("**/api/agent/conversations/*/messages", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "event: run.started",
          'data: {"runId":"r4","messageId":"m-empty","model":"deepseek-flash","creditBalance":1195}',
          "",
          "event: message.completed",
          'data: {"messageId":"m-empty","model":"deepseek-flash","inputTokens":120,"outputTokens":0,"creditsUsed":5,"creditBalance":1195}',
          "",
          "",
        ].join("\n"),
      }),
    );
    await page.goto("/zh/chat");
    // Guard: a signed-out redirect would make these assertions meaningless.
    await expect(page).toHaveURL(/\/zh\/chat$/);
    await page.locator("textarea").fill("return nothing");
    await page.keyboard.press("Enter");
    const billing = page.getByTestId("chat-error-billing");
    await expect(billing).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("chat-error")).toContainText("空回答");
    // The persisted message carries credits_refunded: false, so the copy states
    // the settled outcome rather than implying the run was free.
    await expect(billing).toHaveAttribute("data-billing", "settled");
    await expect(billing).toContainText("已记入用量记录");
  });
});

test.describe("Gateway console with the upgraded model", () => {
  test("model usage, request history and wallet rows still render", async ({ page }) => {
    await page.route("**/me", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(USER) }));
    await page.goto("/zh/gateway");
    await expect(page.getByRole("heading", { name: "AI API Gateway" })).toBeVisible();
    // Usage/keys/requests fall back to their empty states without a session; the
    // page must stay usable rather than breaking on the new model id.
    await expect(page.getByText(/Gateway 数据暂不可用|API 可用余额/).first()).toBeVisible();
  });
});
