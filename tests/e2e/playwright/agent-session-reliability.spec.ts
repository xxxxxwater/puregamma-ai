import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Agent session reliability (frontend; every endpoint stubbed).
 *
 * Server events are the truth: duplicates and other runs' frames are ignored,
 * a dropped connection reads as "reconnecting" until the server says how the
 * run ended, a reload re-attaches to a run still in progress, a retry after a
 * request that got no answer re-uses the same client_request_id, and the
 * stop / approval / evidence / history surfaces behave by keyboard too.
 */

const USER = { user: { id: "u1", email: "u@example.invalid", name: "U", role: "user", plan: "Pro", credit_balance: 1200, auth_provider: "email" } };
const QUOTA = { plan: "Pro", used: 0, limit: 200, remaining: 200, concurrent_limit: 2, running: 0, credit_balance: 1200 };
const CAPABILITIES = {
  capabilities: { plan: "Pro", allowed_data_sources: ["all"], allowed_skills: ["all"], max_attachments: 5 },
  quota: QUOTA,
  models: [{ id: "default", display_name: "Default", description: "", provider: "default", available: true, reason: null, credit_cost: null }],
  skills: [],
  plugins: [{ id: "market", name: "Market data", description: "Quotes", enabled: true, reason: null, service: "pgMarketData", tools: ["market_snapshot"] }],
  plugin_counts: { total: 1, enabled: 1, tools: 1 },
};

function conversation(id: string, title: string, archived = false) {
  return { id, title, status: archived ? "archived" : "active", archived_at: archived ? "2026-10-27T00:00:00+00:00" : null, created_at: "2026-10-27T00:00:00+00:00", updated_at: "2026-10-27T00:00:00+00:00", permission_mode: "workspace-write" };
}

function message(id: string, role: "user" | "assistant", content: string, extra: Record<string, unknown> = {}) {
  return { id, conversation_id: "c1", role, content, status: "completed", model: role === "assistant" ? "deepseek-flash" : null, input_tokens: 1, output_tokens: 1, credits_refunded: false, created_at: "2026-10-27T00:00:00+00:00", sources: [], ...extra };
}

function sse(frames: Array<[string, Record<string, unknown>]>) {
  return frames.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}

type Snapshot = { messages: unknown[]; active_run_id?: string | null; pending_approvals?: unknown[] };

async function stubChat(page: Page, options: { conversations?: unknown[]; snapshot?: () => Snapshot } = {}) {
  const conversations = options.conversations ?? [conversation("c1", "BTC review")];
  await page.route("**/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/gateway/catalog*", (route) => route.fulfill({ json: { data: [] } }));
  await page.route("**/api/frontend/plugins*", (route) => route.fulfill({ json: { plugins: [] } }));
  await page.route("**/api/agent/capabilities", (route) => route.fulfill({ json: CAPABILITIES }));
  await page.route("**/api/agent/quota", (route) => route.fulfill({ json: QUOTA }));
  await page.route("**/api/agent/quote", (route) => route.fulfill({ json: { estimated_min: 2, estimated_max: 4, reservation_amount: 4 } }));
  await page.route("**/api/agent/workspace-capabilities", (route) => route.fulfill({ json: { max_file_bytes: 10485760, max_files: 8, file_types: ["txt", "png"], permission_modes: ["read-only", "workspace-write"] } }));
  await page.route("**/api/agent/conversations", (route) => route.fulfill({ json: { conversations } }));
  await page.route("**/api/agent/conversations/*", (route: Route) => {
    if (route.request().method() !== "GET") return route.fulfill({ json: { conversation: conversations[0] } });
    const snap = options.snapshot ? options.snapshot() : { messages: [] };
    return route.fulfill({ json: { conversation: conversations[0], active_run_id: null, active_run_message_id: null, pending_approvals: [], ...snap } });
  });
}

async function ask(page: Page, text: string) {
  await page.getByTestId("chat-composer-input").fill(text);
  await page.keyboard.press("Enter");
}

test.describe("Agent session reliability", () => {
  test("duplicate and foreign frames are ignored; tool steps carry server times", async ({ page }) => {
    let completed = false;
    await stubChat(page, { snapshot: () => ({ messages: completed ? [message("mu", "user", "q"), message("ma", "assistant", "Hello world")] : [] }) });
    await page.route("**/api/agent/conversations/*/messages", (route) => {
      completed = true;
      return route.fulfill({ contentType: "text/event-stream", body: sse([
        ["run.started", { runId: "r1", messageId: "ma", model: "deepseek-flash", seq: 1, at: "2026-10-28T08:00:00Z" }],
        ["tool.started", { toolCallId: "t1", tool: "market_snapshot", arguments: { symbol: "BTC", api_key: "••••" }, seq: 2, at: "2026-10-28T08:00:01Z" }],
        ["tool.started", { toolCallId: "t1", tool: "market_snapshot", seq: 2, at: "2026-10-28T08:00:01Z" }],
        ["tool.completed", { toolCallId: "t1", tool: "market_snapshot", summary: "BTC 64,000", latencyMs: 1200, seq: 3, at: "2026-10-28T08:00:02Z" }],
        ["message.delta", { messageId: "ma", delta: "Hello ", seq: 4 }],
        ["message.delta", { messageId: "ma", delta: "Hello ", seq: 4 }],
        ["message.delta", { messageId: "ma", delta: "STALE ", seq: 4 }],
        ["tool.started", { toolCallId: "tx", tool: "other_run_tool", runId: "r-other", seq: 5 }],
        ["message.delta", { messageId: "ma", delta: "world", seq: 6 }],
      ]) });
    });
    await page.goto("/en/chat/c1");
    await ask(page, "q");
    // While streaming, the duplicated delta must not appear twice.
    const timeline = page.getByTestId("tool-timeline");
    await expect(timeline).toContainText("Market snapshot");
    await expect(timeline).not.toContainText("Other run tool");
    await expect(timeline.locator("li")).toHaveCount(1);
    await timeline.getByText("Market snapshot").click();
    await expect(timeline).toContainText("1.2s");
    await expect(timeline).toContainText('"api_key": "••••"');
    await expect(page.getByText("Hello world")).toBeVisible();
    await expect(page.getByText(/Hello Hello|STALE/)).toHaveCount(0);
  });

  test("a dropped stream reads as reconnecting and ends with the server's outcome", async ({ page }) => {
    let snapshots = 0;
    let polls = 0;
    let sent = false;
    await stubChat(page, {
      snapshot: () => {
        snapshots += 1;
        if (!sent) return { messages: [] };
        // While the run is active the snapshot points at it; afterwards the
        // persisted answer is complete.
        return polls < 2 ? { messages: [message("mu", "user", "q")], active_run_id: "r1" } : { messages: [message("mu", "user", "q"), message("ma", "assistant", "Recovered answer")], active_run_id: null };
      },
    });
    await page.route("**/api/agent/runs/r1/events*", async (route) => {
      polls += 1;
      await route.fulfill({ json: { runId: "r1", status: polls < 2 ? "running" : "completed", messageId: "ma", conversationId: "c1", lastSeq: 3, truncated: false, events: polls < 2 ? [{ seq: 3, type: "tool.started", data: { toolCallId: "t9", tool: "search_news", at: "2026-10-28T08:00:03Z" } }] : [] } });
    });
    await page.route("**/api/agent/conversations/*/messages", (route) => { sent = true; return route.fulfill({ contentType: "text/event-stream", body: sse([
      ["run.started", { runId: "r1", messageId: "ma", model: "deepseek-flash", seq: 1 }],
      ["message.delta", { messageId: "ma", delta: "partial", seq: 2 }],
    ]) }); });
    await page.goto("/en/chat/c1");
    await ask(page, "q");
    await expect(page.getByTestId("chat-reconnecting")).toBeVisible();
    await expect(page.getByTestId("chat-error")).toHaveCount(0);
    await expect(page.getByText("Recovered answer")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("chat-recovered")).toBeVisible();
    await expect(page.getByTestId("chat-error")).toHaveCount(0);
    expect(snapshots).toBeGreaterThan(1);
  });

  test("a reload re-attaches to a run still in progress", async ({ page }) => {
    let polls = 0;
    await stubChat(page, { snapshot: () => (polls < 2 ? { messages: [message("mu", "user", "q")], active_run_id: "r7" } : { messages: [message("mu", "user", "q"), message("ma", "assistant", "Finished on the server")], active_run_id: null }) });
    await page.route("**/api/agent/runs/r7/events*", async (route) => {
      polls += 1;
      const after = Number(new URL(route.request().url()).searchParams.get("after") || 0);
      const events = [{ seq: 2, type: "tool.started", data: { toolCallId: "t1", tool: "get_market_quote" } }, { seq: 3, type: "tool.completed", data: { toolCallId: "t1", tool: "get_market_quote", summary: "ok" } }].filter((event) => event.seq > after);
      await route.fulfill({ json: { runId: "r7", status: polls < 2 ? "running" : "completed", messageId: "ma", conversationId: "c1", lastSeq: 3, truncated: false, events } });
    });
    await page.goto("/en/chat/c1");
    await expect(page.getByTestId("chat-observing")).toBeVisible();
    await expect(page.getByTestId("tool-timeline")).toContainText("Get market quote");
    await expect(page.getByText("Finished on the server")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("chat-observing")).toHaveCount(0);
  });

  test("a request that got no answer is retried with the same client_request_id", async ({ page }) => {
    const keys: string[] = [];
    await stubChat(page, { snapshot: () => ({ messages: keys.length > 1 ? [message("mu", "user", "retry me"), message("ma", "assistant", "Answered once")] : [] }) });
    await page.route("**/api/agent/conversations/*/messages", async (route) => {
      keys.push(route.request().postDataJSON().client_request_id);
      if (keys.length === 1) return route.abort("failed");
      return route.fulfill({ contentType: "text/event-stream", body: sse([
        ["run.started", { runId: "r2", messageId: "ma", model: "deepseek-flash", seq: 1 }],
        ["message.delta", { messageId: "ma", delta: "Answered once", seq: 2 }],
        ["message.completed", { messageId: "ma", model: "deepseek-flash", seq: 3 }],
      ]) });
    });
    await page.goto("/en/chat/c1");
    await ask(page, "retry me");
    const retry = page.getByTestId("chat-retry-safely");
    await expect(retry).toBeVisible({ timeout: 15000 });
    await retry.click();
    await expect(page.getByText("Answered once")).toBeVisible();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toMatch(/^web-/);
    expect(keys[1]).toBe(keys[0]);
  });

  test("a duplicate submission follows the existing run instead of starting another", async ({ page }) => {
    let polled = false;
    await stubChat(page, { snapshot: () => ({ messages: polled ? [message("mu", "user", "dup"), message("ma", "assistant", "The first run's answer")] : [] }) });
    await page.route("**/api/agent/conversations/*/messages", (route) => route.fulfill({ status: 409, json: { detail: { code: "DUPLICATE_SUBMISSION", runId: "r-first", status: "running", messageId: "ma" } } }));
    await page.route("**/api/agent/runs/r-first/events*", (route) => { polled = true; return route.fulfill({ json: { runId: "r-first", status: "completed", messageId: "ma", conversationId: "c1", lastSeq: 0, truncated: false, events: [] } }); });
    await page.goto("/en/chat/c1");
    await ask(page, "dup");
    await expect(page.getByText("The first run's answer")).toBeVisible();
    await expect(page.getByTestId("chat-error")).toHaveCount(0);
  });

  test("stop cancels the run once and says what stopping means", async ({ page }) => {
    const cancels: string[] = [];
    await stubChat(page, { snapshot: () => ({ messages: [message("mu", "user", "long task")], active_run_id: cancels.length ? null : "r3" }) });
    // The re-attached run keeps running until it is canceled.
    await page.route("**/api/agent/runs/r3/events*", (route) => route.fulfill({ json: { runId: "r3", status: cancels.length ? "canceled" : "running", messageId: "ma", conversationId: "c1", lastSeq: 1, truncated: false, events: [] } }));
    await page.route("**/api/agent/runs/*/cancel", (route) => { cancels.push(route.request().url()); return route.fulfill({ json: { id: "r3", status: "canceled" } }); });
    await page.goto("/en/chat/c1");
    await expect(page.getByTestId("chat-observing")).toBeVisible();
    await page.getByTestId("chat-stop").click();
    await expect(page.getByTestId("chat-stopped")).toContainText("not undone");
    await expect(page.getByTestId("chat-observing")).toHaveCount(0);
    expect(cancels).toHaveLength(1);
    expect(cancels[0]).toContain("/api/agent/runs/r3/cancel");
  });

  test("a pending tool approval states action, scope, authority and validity", async ({ page }) => {
    let decision = "";
    await stubChat(page, { snapshot: () => ({ messages: [], pending_approvals: [{ toolCallId: "t5", tool: "update_watchlist", arguments: { symbol: "BTC", token: "••••" }, expiresAt: new Date(Date.now() + 90_000).toISOString(), permissionMode: "workspace-write" }] }) });
    await page.route("**/api/agent/tool-calls/t5/approval", (route) => { decision = route.request().postDataJSON().decision; return route.fulfill({ json: { id: "t5", decision } }); });
    await page.goto("/en/chat/c1");
    const card = page.getByTestId("tool-approval");
    await expect(card).toContainText("Update watchlist");
    await expect(card).toContainText("This conversation only");
    await expect(card).toContainText("Ask before changes");
    await expect(card.getByTestId("tool-approval-validity")).toContainText(/\d+s/);
    await card.getByRole("button", { name: "Allow once" }).click();
    await expect.poll(() => decision).toBe("approved");
    await expect(card).toHaveCount(0);
  });

  test("a citation marker opens the evidence inspector at that source and returns focus", async ({ page }) => {
    const answer = message("ma", "assistant", "BTC broke its range [1]. Funding is neutral [2].", {
      sources: [
        { provider: "ChainCatcher", title: "BTC breaks range", url: "https://example.com/a", published_at: new Date(Date.now() - 30 * 60_000).toISOString(), source_timestamp: null, fetched_at: new Date().toISOString(), citation_index: 1 },
        { provider: "Coinglass", title: "Funding snapshot", url: null, published_at: "2026-01-01T00:00:00Z", source_timestamp: null, fetched_at: "2026-01-01T00:05:00Z", citation_index: 2 },
      ],
      context: { evidence: { sufficient: false, missing: ["onchain"], source_count: 2 } },
    });
    await stubChat(page, { snapshot: () => ({ messages: [message("mu", "user", "q"), answer] }) });
    await page.goto("/en/chat/c1");
    const marker = page.locator('a[href="#cite-ma-2"]');
    await expect(marker).toBeVisible();
    await marker.click();
    const inspector = page.getByTestId("evidence-inspector");
    await expect(inspector).toBeVisible();
    await expect(inspector.getByTestId("evidence-status")).toContainText("onchain");
    await expect(inspector.locator('[data-citation-index="2"]')).toBeFocused();
    await expect(inspector.locator('[data-citation-index="2"]')).toContainText("May be stale");
    await page.keyboard.press("Escape");
    await expect(inspector).toHaveCount(0);
    await expect(marker).toBeFocused();
  });

  test("history: search, archive, and a failed delete restores the row", async ({ page }) => {
    await stubChat(page, { conversations: [conversation("c1", "BTC review"), conversation("c2", "ETH funding"), conversation("c3", "Old idea", true)], snapshot: () => ({ messages: [] }) });
    await page.route("**/api/agent/conversations/c2", (route) => (route.request().method() === "DELETE" ? route.fulfill({ status: 503, json: { detail: "down" } }) : route.fulfill({ json: { conversation: conversation("c2", "ETH funding", true) } })));
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/en/chat/c1");
    const history = page.locator("#chat-history-panel");
    await history.getByTestId("chat-history-search").fill("eth");
    await expect(history.getByText("ETH funding")).toBeVisible();
    await expect(history.getByText("BTC review")).toHaveCount(0);
    // Row actions appear on hover or keyboard focus within the row.
    await history.getByText("ETH funding").hover();
    await history.getByRole("button", { name: "Delete conversation: ETH funding" }).click();
    await expect(history.getByRole("alert")).toBeVisible();
    await expect(history.getByText("ETH funding")).toBeVisible();
    await history.getByTestId("chat-history-search").fill("");
    await history.getByRole("button", { name: /Archived 1/ }).click();
    await expect(history.getByText("Old idea")).toBeVisible();
  });

  test("skills are listed with their tools and the reason one is unavailable", async ({ page }) => {
    await stubChat(page, { snapshot: () => ({ messages: [] }) });
    const skill = (name: string, extra: Record<string, unknown>) => ({ skill_id: name, slug: name, name, description: `${name} description`, publisher: "PureGamma", scope: "official", status: "published", current_version: "1.0.0", asset_classes: [], data_sources: [], tool_allowlist: ["get_market_quote", "search_news"], risk_level: "low", allow_autopilot: false, allow_order_intent: false, billing_type: "included", evidence: { required: true, require_source_timestamp: true, require_citation_links: true }, runtime: { max_calls_per_hour: 10, max_credits_per_run: 5, timeout_seconds: 60, human_confirmation_required: false }, installed: true, enabled: true, ...extra });
    await page.route("**/api/agent/capabilities", (route) => route.fulfill({ json: { ...CAPABILITIES, skills: [skill("Market research", {}), skill("Options analysis", { status: "review" })] } }));
    await page.goto("/en/chat/c1");
    await page.getByText("Research settings").click();
    const panel = page.getByTestId("agent-skills");
    await expect(panel).toContainText("1/2 available");
    await expect(panel).toContainText("get_market_quote, search_news");
    await expect(panel).toContainText("In review, not published");
    await expect(panel).toContainText("never raise a tool permission");
  });

  test("an upload refused by the edge proxy (bare 413) is reported as a size limit", async ({ page }) => {
    await stubChat(page, { snapshot: () => ({ messages: [] }) });
    await page.route("**/api/agent/attachments?*", (route) => route.fulfill({ status: 413, contentType: "text/html", body: "<html><body>413 Request Entity Too Large</body></html>" }));
    await page.goto("/en/chat/c1");
    await page.locator('input[type="file"]').setInputFiles({ name: "big.txt", mimeType: "text/plain", buffer: Buffer.from("x") });
    await expect(page.getByRole("alert").filter({ hasText: "big.txt: File count or size limit exceeded" })).toBeVisible();
  });

  test("desktop collapse survives a reload", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await stubChat(page, { snapshot: () => ({ messages: [] }) });
    await page.goto("/en/chat/c1");
    await page.getByRole("button", { name: "Collapse conversation history" }).click();
    await expect(page.getByRole("button", { name: "Expand conversation history" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Expand conversation history" })).toBeVisible();
  });

  test("a prompt handed over in the URL pre-fills but does not send", async ({ page }) => {
    let posts = 0;
    await stubChat(page, { snapshot: () => ({ messages: [] }) });
    await page.route("**/api/agent/conversations/*/messages", (route) => { posts += 1; return route.abort(); });
    await page.goto("/en/chat?prompt=" + encodeURIComponent("Explain BTC funding"));
    await expect(page.getByTestId("chat-composer-input")).toHaveValue("Explain BTC funding");
    expect(posts).toBe(0);
  });
});

test.describe("phone drawers", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("chat history drawer returns focus on Escape and after choosing a conversation", async ({ page }) => {
    await stubChat(page, { conversations: [conversation("c1", "BTC review"), conversation("c2", "ETH funding")], snapshot: () => ({ messages: [] }) });
    await page.goto("/en/chat/c1");
    const trigger = page.getByTestId("chat-history-trigger");
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Conversation history" });
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.getByRole("dialog", { name: "Conversation history" }).getByText("ETH funding").click();
    await expect(page.getByRole("dialog", { name: "Conversation history" })).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("the closed navigation drawer is hidden, untabbable and does not bleed onto the page", async ({ page }) => {
    await stubChat(page, { snapshot: () => ({ messages: [] }) });
    await page.goto("/en/chat/c1");
    const drawer = page.locator("#mobile-primary-nav");
    await expect(drawer).toHaveAttribute("data-state", "closed");
    await expect(drawer).toBeHidden();
    await expect(page.getByRole("dialog", { name: "Primary navigation" })).toHaveCount(0);
    const box = await drawer.boundingBox();
    expect(box === null || box.x + box.width <= 0).toBeTruthy();
    const menu = page.getByTestId("nav-menu-button");
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await menu.click();
    await expect(page.getByRole("dialog", { name: "Primary navigation" })).toBeVisible();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await expect.poll(() => page.evaluate(() => document.getElementById("mobile-primary-nav")?.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveAttribute("data-state", "closed");
    await expect(menu).toBeFocused();
  });
});
