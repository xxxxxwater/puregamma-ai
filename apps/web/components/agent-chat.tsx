"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Bot, CheckCircle2, CircleAlert, Compass, Database, FlaskConical, Loader2, MessageSquarePlus, PanelLeftClose, PanelLeftOpen, RefreshCw, SearchCheck, ShieldCheck, Target, Trash2, Wrench, X } from "lucide-react";
import { ChatWorkspaceComposer, AttachmentCards } from "@/components/chat-workspace-composer";
import { setAgentPermission, approveAgentTool, type AgentPermissionMode } from "@/lib/api";
import { ReportMarkdown } from "@/components/puregamma";
import { ContextControls, nextActionLabel, nextActionPrompt, StrategyToolResult } from "@/components/chat-panels";
import { AgentStageIndicator, nextAgentStage, type AgentStage } from "@/components/ocean/agent-stage-indicator";
import { OceanShell } from "@/components/ocean/ocean-shell";
import { RippleEffect } from "@/components/ocean/ripple-effect";
import { type Locale, withLocale } from "@/i18n/routing";
import { AgentAttachment, AgentCapabilities, AgentConversation, AgentEvidenceSummary, AgentMessage, AgentModelOption, AgentRuntimePlan, AgentPluginEntry, AgentSource, cancelAgentRun, createAgentConversation, deleteAgentConversation, deleteAllAgentConversations, getAgentCapabilities, getAgentConversation, getAgentConversations, getAgentQuota, getAgentQuote, getGatewayCatalog, getMe, streamAgentMessage } from "@/lib/api";
import { billingNotice, describeChatFailure, type ChatFailure } from "@/lib/chat-errors";
import { FLASH_ALIAS_ID, FLASH_MODEL_ID, flashAvailability, platformDefaultModelName } from "@/lib/model-catalog";
import { getMessageNamespace } from "@/lib/translations";
import { publishCreditBalance } from "@/lib/user-state";

const DATA_SOURCES = ["market", "rss", "fintwit", "x-twitter", "bloomberg", "portfolio", "options"];

/**
 * The Agent's `default` selection is a routing sentinel, not a model id: the
 * backend resolves it to the platform model. The request body must keep sending
 * `default`, but the user should read the model that will actually answer.
 *
 * `catalogName` is the catalog's own `display_name` for the platform default
 * model, so the label follows the deployment instead of a literal in this file.
 * The i18n string is only a fallback for when the catalog is unreachable.
 */
function agentModelLabel(model: AgentModelOption, copy: ModelUpgradeCopy, catalogName: string | null) {
  if (model.id === "default") return catalogName || copy.chat.badgeLive;
  return model.display_name;
}

function agentModelSuffix(model: AgentModelOption, zh: boolean) {
  if (model.id === "default") return zh ? " · 平台默认路由" : " · platform default route";
  if (model.available) return zh ? " · 按实际使用计费" : " · usage-metered";
  if (model.reason === "plan_required") return zh ? " · 需要 Max/Enterprise" : " · Max/Enterprise required";
  return zh ? " · 当前不可用" : " · unavailable";
}

type ModelUpgradeCopy = ReturnType<typeof getMessageNamespace<"model-upgrade">>;

/**
 * Turn the model id recorded on a message into the name a user recognises.
 *
 * Historical messages keep their real recorded model: a conversation answered
 * by another provider must never be relabelled as the platform default, so only
 * the ids that really resolve to the upgraded model are mapped.
 */
function bylineModelLabel(
  model: string | null | undefined,
  copy: ModelUpgradeCopy,
  catalogName: string | null,
  catalog: ReadonlyMap<string, string>,
) {
  const id = (model || "").trim();
  const platformName = catalogName || copy.chat.badgeLive;
  if (!id || id === "default" || id === FLASH_MODEL_ID || id === FLASH_ALIAS_ID) return platformName;
  // The label comes from the server's catalog, so retiring or renaming a model
  // needs no client release and the byline can never name a model the server
  // would refuse.
  const known = catalog.get(id);
  if (known) return known;
  if (id === "deepseek-v4-pro") return "DeepSeek V4 Pro";
  return id;
}

export function AgentChat({ locale, initialConversationId }: { locale: Locale; initialConversationId?: string }) {
  const router = useRouter();
  const zh = locale === "zh";
  const modelCopy = getMessageNamespace(locale, "model-upgrade");
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [conversationId, setConversationId] = useState(initialConversationId || "");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ChatFailure | null>(null);
  const [toolStatus, setToolStatus] = useState<Array<{ id: string; tool: string; status: string }>>([]);
  const [toolResults, setToolResults] = useState<Array<{ tool: string; data: Record<string, unknown> }>>([]);
  const [stage, setStage] = useState<AgentStage | null>(null);
  const [quota, setQuota] = useState<{ remaining: number | null; limit: number | null; credit_balance: number } | null>(null);
  const [capabilities, setCapabilities] = useState<AgentCapabilities | null>(null);
  const [models, setModels] = useState<AgentModelOption[]>([]);
  // Built-in capability inventory, straight from `/agent/capabilities`.
  const [plugins, setPlugins] = useState<AgentPluginEntry[]>([]);
  const [pluginCounts, setPluginCounts] = useState<{ total: number; enabled: number; tools: number } | null>(null);
  const [selectedModel, setSelectedModel] = useState("default");
  const [dataSources, setDataSources] = useState<string[]>([]);
  /* Small-screen conversation history. The aside is `hidden` below `lg`, so
     without this the conversation list, "new conversation" and "delete all
     history" were unreachable on a phone — an old conversation could only be
     reopened from the dashboard or by typing its URL. */
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false);
  const historyPanelRef = useRef<HTMLElement | null>(null);
  const historyTriggerRef = useRef<HTMLButtonElement | null>(null);
  // id -> display name, straight from `GET /agent/capabilities`.
  const modelLabels = useMemo(() => new Map(models.map((model) => [model.id, model.display_name])), [models]);
  const [customPrompt, setCustomPrompt] = useState("");
  const [researchMode, setResearchMode] = useState(true);
  const [permission, setPermission] = useState<AgentPermissionMode>("workspace-write");
  const [uploading, setUploading] = useState(false);
  const [approval, setApproval] = useState<{toolCallId: string; tool: string; arguments: Record<string, unknown>} | null>(null);
  const [approving, setApproving] = useState(false);
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const [runtimePlan, setRuntimePlan] = useState<AgentRuntimePlan | null>(null);
  const [evidenceStatus, setEvidenceStatus] = useState<AgentEvidenceSummary | null>(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const [availability, setAvailability] = useState<"checking" | "published" | "pending" | "unavailable" | "unverified">("checking");
  /** Catalog display name for the platform default model; null until known. */
  const [defaultModelName, setDefaultModelName] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  /* Drawer behaviour: Escape closes it, background scroll is locked while it is
     open, focus moves into the panel, and focus returns to the trigger when it
     closes. All of these are what make a drawer usable with a keyboard rather
     than merely visible. */
  useEffect(() => {
    if (!mobileHistoryOpen) return;
    const panel = historyPanelRef.current;
    const focusable = panel?.querySelector<HTMLElement>(
      'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileHistoryOpen(false);
        return;
      }
      // Keep Tab inside the open drawer.
      if (event.key !== "Tab" || !panel) return;
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileHistoryOpen]);

  const closeMobileHistory = () => {
    setMobileHistoryOpen(false);
    historyTriggerRef.current?.focus();
  };
  const activeRunRef = useRef("");
  /** Guards against a double submit (Enter plus click, or a slow network) firing two runs. */
  const sendingRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  const loadConversations = async () => {
    const result = await getAgentConversations();
    // A payload without `conversations` must yield an empty history rather than
    // an undefined list that later `.map()` calls throw on.
    const rows = Array.isArray(result.conversations) ? result.conversations : [];
    setConversations(rows);
    return rows;
  };

  const openConversation = async (id: string) => {
    if (busy || uploading) return;
    const result = await getAgentConversation(id);
    setApproval(result.pending_approvals?.[0] ?? null);
    setConversationId(id);
    setPermission(result.conversation.permission_mode || "workspace-write");
    setMessages(result.messages);
    setFailure(null);
  };

  useEffect(() => {
    let active = true;
    // The default model's name AND its catalog state are read from the catalog
    // this deployment serves, never asserted from copy.
    void getGatewayCatalog(locale)
      .then((catalog) => {
        if (!active) return;
        setAvailability(flashAvailability(catalog).uiState);
        setDefaultModelName(platformDefaultModelName(catalog));
      })
      .catch(() => { if (active) setAvailability("unverified"); });
    Promise.all([getMe(), loadConversations(), getAgentCapabilities()])
      .then(async ([, rows, access]) => {
        if (!active) return;
        // `Array.isArray` rather than trusting the field: a capabilities payload
        // that omits `models` must degrade to an empty selector, not
        // throw during render and take the whole chat surface down with it.
        setQuota(access.quota);
        setCapabilities(access.capabilities);
        setModels(Array.isArray(access.models) ? access.models : []);
        const target = initialConversationId || rows[0]?.id;
        if (target) await openConversation(target);
      })
      .catch((reason: Error & { status?: number }) => {
        if (reason.status === 401) router.replace(`${withLocale(locale, "/login")}?returnTo=${encodeURIComponent(withLocale(locale, "/chat"))}`);
        else if (active) setFailure(describeChatFailure(locale, reason));
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; controllerRef.current?.abort(); };
  }, [initialConversationId, locale, router]);

  useEffect(() => {
    if (followRef.current) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, toolStatus]);

  const createNew = async () => {
    if (busy || uploading) return;
    setPermission("workspace-write");
    setApproval(null);
    const result = await createAgentConversation();
    setConversations((current) => [result.conversation, ...current]);
    setConversationId(result.conversation.id);
    setMessages([]);
    router.push(withLocale(locale, `/chat/${result.conversation.id}`));
  };

  const deleteConversation = async (id: string) => {
    setConversations((current) => current.filter((conversation) => conversation.id !== id));
    if (conversationId === id) {
      const remaining = conversations.filter((conversation) => conversation.id !== id);
      if (remaining.length) {
        router.push(withLocale(locale, `/chat/${remaining[0].id}`));
        openConversation(remaining[0].id);
      } else {
        setConversationId("");
        setMessages([]);
        router.push(withLocale(locale, "/chat"));
      }
    }
    deleteAgentConversation(id).catch(() => {});
  };

  const deleteAll = async () => {
    setConversations([]);
    setConversationId("");
    setMessages([]);
    router.push(withLocale(locale, "/chat"));
    deleteAllAgentConversations().catch(() => {});
  };

  const ensureConversation = async () => {
    if (conversationId) return conversationId;
    const result = await createAgentConversation();
    setConversationId(result.conversation.id);
    setConversations((current) => [result.conversation, ...current]);
    window.history.replaceState(null, "", withLocale(locale, `/chat/${result.conversation.id}`));
    return result.conversation.id;
  };

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    // A file the user removed is still shown (so the conversation stays honest)
    // but must never be sent: its bytes are gone.
    const outgoing = attachments.filter((file) => !file.removed);
    const content = input.trim() || (outgoing.length ? (zh ? "请分析所附文件。" : "Please analyze the attached files.") : "");
    // A ref, not just the `busy` state: two submissions in the same tick would
    // both read the pre-update state and start two runs.
    if (!content || busy || uploading || sendingRef.current) return;
    sendingRef.current = true;
    setBusy(true);
    setFailure(null);
    setToolStatus([]);
    setToolResults([]);
    setRuntimePlan(null);
    setEvidenceStatus(null);
    setStage(null);
    followRef.current = true;
    let assistantId = "";
    let assistantContent = "";
    let completed = false;
    /** True once an SSE event reported the run's own failure and its billing. */
    let failureReported = false;
    try {
      const id = await ensureConversation();
      await setAgentPermission(id, permission, permission === "full-access");
      setInput("");
      const now = new Date().toISOString();
      // Capabilities are built-in plugins now: the Agent picks its own sources and
      // tools from the goal. The request carries no skill selection at all.
      const context = { research_mode: researchMode, data_sources: researchMode ? dataSources : [], custom_prompt: researchMode ? customPrompt : "", attachments: outgoing, model: selectedModel, permission_mode: permission };
      setMessages((current) => [...current, { id: `local-${Date.now()}`, conversation_id: id, role: "user", content, status: "completed", input_tokens: 0, output_tokens: 0, created_at: now, context, sources: [] }]);
      const controller = new AbortController();
      controllerRef.current = controller;
      await streamAgentMessage(id, content, locale, controller.signal, ({ event: eventName, data }) => {
        if (eventName === "run.started") {
          activeRunRef.current = String(data.runId || "");
          assistantId = String(data.messageId || `assistant-${Date.now()}`);
          setStage("understanding");
          setMessages((current) => [...current, { id: assistantId, conversation_id: id, role: "assistant", content: "", status: "streaming", model: String(data.model || selectedModel), input_tokens: 0, output_tokens: 0, created_at: new Date().toISOString(), sources: [] }]);
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        } else if (eventName === "plan.ready") {
          setStage((current) => nextAgentStage(current, "selecting"));
          setRuntimePlan({
            intent: String(data.intent || "general_research"),
            assets: Array.isArray(data.assets) ? data.assets.map(String) : [],
            evidence_requirements: Array.isArray(data.evidenceRequirements) ? data.evidenceRequirements.map(String) : [],
            auto_selected_skills: Boolean(data.autoSelectedSkills),
            clarification_recommended: Boolean(data.clarificationRecommended),
          });
        } else if (eventName === "message.delta") {
          setStage((current) => nextAgentStage(current, "preparing"));
          const delta = String(data.delta || "");
          if (String(data.messageId) === assistantId) assistantContent += delta;
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, content: `${message.content}${delta}` } : message));
        } else if (eventName === "tool.started") {
          setStage((current) => nextAgentStage(current, "collecting"));
          setToolStatus((current) => [...current, { id: String(data.toolCallId || `${data.tool}-${Date.now()}`), tool: String(data.tool), status: zh ? "检索中" : "retrieving" }]);
        } else if (eventName === "tool.completed") {
          setApproval(current => current?.toolCallId === String(data.toolCallId) ? null : current);
          const callId = String(data.toolCallId || "");
          setToolStatus((current) => current.map((item) => (item.id === callId || (!callId && item.tool === String(data.tool)) ? { ...item, status: data.error ? (zh ? "失败" : "failed") : (zh ? "完成" : "complete") } : item)));
          if (data.data && typeof data.data === "object") setToolResults((current) => [...current, { tool: String(data.tool), data: data.data as Record<string, unknown> }]);
        } else if (eventName === "citation") {
          const source: AgentSource = { provider: String(data.provider), title: String(data.title), url: data.url ? String(data.url) : null, published_at: data.publishedAt ? String(data.publishedAt) : null, source_timestamp: data.sourceTimestamp ? String(data.sourceTimestamp) : null, fetched_at: String(data.fetchedAt), citation_index: Number(data.index) };
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, sources: [...message.sources, source] } : message));
        } else if (eventName === "evidence.ready") {
          setStage((current) => nextAgentStage(current, "validating"));
          setEvidenceStatus(data as unknown as AgentEvidenceSummary);
        } else if (eventName === "approval.required") {
          setApproval(data as unknown as {toolCallId: string; tool: string; arguments: Record<string, unknown>});
        } else if (eventName === "message.completed") {
          setStage(null);
          completed = true;
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "completed", model: String(data.model || message.model || ""), input_tokens: Number(data.inputTokens || 0), output_tokens: Number(data.outputTokens || 0), credits_used: Number(data.creditsUsed || 0), context: { data_sources: [], skills: [], custom_prompt: "", attachments: [], model: String(data.model || message.model || ""), runtime: runtimePlan ? { ...runtimePlan, next_actions: Array.isArray(data.nextActions) ? data.nextActions.map(String) : [] } : undefined, evidence: data.evidence as AgentEvidenceSummary | undefined } } : message));
          setQuota((current) => current ? { ...current, credit_balance: Number(data.creditBalance ?? current.credit_balance) } : current);
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        } else if (eventName === "run.failed") {
          setStage(null);
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "failed", error_code: String(data.code), error_message: String(data.message) } : message));
          // `stream_run` refunds before emitting run.failed, so this run's
          // billing status is known here — but it is asserted from that refund,
          // not inferred from the error type.
          setFailure(describeChatFailure(locale, null, { kind: "generic", refunded: true }));
          failureReported = true;
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        } else if (eventName === "run.canceled") {
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        }
      }, context);
      if (completed) setAttachments([]);
      // Re-read the persisted messages: the reload carries `credits_refunded`,
      // the only authoritative settlement result for this run.
      const refreshed = await getAgentConversation(id);
      setMessages(refreshed.messages);
      const settled = refreshed.messages.find((message) => message.id === assistantId);
      // A run can finish without producing any text. Say so instead of leaving
      // a blank bubble that looks like a rendering bug, and report the recorded
      // billing state rather than assuming the empty answer was free.
      //
      // `failureReported` matters: when `run.failed` already stated this run's
      // billing from the refund it issued, an inferred failure must not replace
      // it with a weaker "unknown".
      if (!failureReported && completed && !assistantContent.trim() && assistantId) {
        const emptyFailure = describeChatFailure(locale, null, {
          kind: "empty_answer",
          refunded: settled?.credits_refunded === true,
          settled: settled?.credits_refunded === false,
        });
        setFailure(emptyFailure);
      } else if (!failureReported && assistantId && !completed) {
        // The stream ended cleanly but never emitted `message.completed`: a
        // proxy cut the body without an error. The backend settles what was
        // produced in that case, so state nothing about billing and point at
        // the usage record.
        setMessages((current) => current.map((message) => message.id === assistantId && message.status === "streaming" ? { ...message, status: "failed" } : message));
        setFailure(describeChatFailure(locale, null, {
          kind: "stream_interrupted",
          refunded: settled?.credits_refunded === true,
          settled: settled?.credits_refunded === false,
        }));
      }
      await loadConversations();
      const refreshedQuota = await getAgentQuota();
      setQuota(refreshedQuota);
      publishCreditBalance(refreshedQuota.credit_balance);
    } catch (reason) {
      if ((reason as Error).name === "AbortError") {
        // The user stopped the run; that is a normal outcome, not an error.
      } else if (assistantId && !completed) {
        // The response body died mid-stream. The backend *settles* the tokens
        // already produced on a client disconnect, so this states no billing
        // outcome and points at the usage record instead.
        setMessages((current) => current.map((message) => message.id === assistantId && message.status === "streaming" ? { ...message, status: "failed" } : message));
        setFailure(describeChatFailure(locale, reason, { kind: "stream_interrupted" }));
      } else {
        setFailure(describeChatFailure(locale, reason));
      }
    } finally {
      setApproval(null);
      setBusy(false);
      setStage(null);
      activeRunRef.current = "";
      controllerRef.current = null;
      sendingRef.current = false;
    }
  };

  const stop = async () => {
    if (activeRunRef.current) await cancelAgentRun(activeRunRef.current).catch(() => undefined);
    controllerRef.current?.abort();
    setBusy(false);
    if (conversationId) {
      try {
        const refreshed = await getAgentConversation(conversationId);
        setMessages(refreshed.messages);
        setQuota(await getAgentQuota().catch(() => quota));
      } catch { /* keep current view when refresh fails */ }
    }
  };

  const toggle = (value: string, current: string[], update: (next: string[]) => void) => update(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  const selectedModelOption = models.find((model) => model.id === selectedModel);
  const [creditQuote, setCreditQuote] = useState<{ estimated_min: number; estimated_max: number; reservation_amount?: number; unavailable?: boolean; plan?: AgentRuntimePlan; planned_tools?: string[] } | null>(null);
  useEffect(() => {
    if (!input.trim()) {
      setCreditQuote(null);
      return;
    }
    const timer = window.setTimeout(() => {
      getAgentQuote({ content: input, research_mode: researchMode, data_sources: researchMode ? dataSources : [], custom_prompt: researchMode ? customPrompt : "", attachments, model: selectedModel })
        .then(setCreditQuote)
        .catch(() => setCreditQuote({ estimated_min: 0, estimated_max: 0, unavailable: true }));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [selectedModel, dataSources, attachments, input, customPrompt, researchMode]);
  const estimatedCredits = creditQuote
    ? creditQuote.estimated_min === creditQuote.estimated_max
      ? String(creditQuote.estimated_min)
      : `${creditQuote.estimated_min}-${creditQuote.estimated_max}`
    : "-";
  const starterPrompts = zh ? [
    { title: "BTC 当前市场", body: "结合最新报价和可追溯新闻，分析 BTC 当前市场状态、主要驱动与风险。" },
    { title: "我的组合风险", body: "检查我的组合集中度、主要风险敞口和需要优先关注的变化。" },
    { title: "本周催化剂", body: "梳理未来一周加密与美股最重要的市场催化剂，并区分事实与市场观点。" },
    { title: "策略研究", body: "为 BTC 设计一个 PAPER-first 的研究策略，先说明假设、风险和回测要求。" },
  ] : [
    { title: "BTC market now", body: "Use a fresh quote and traceable sources to assess BTC's current market regime, drivers, and risks." },
    { title: "My portfolio risk", body: "Review my portfolio concentration, major exposures, and the changes I should watch first." },
    { title: "This week's catalysts", body: "Map the most important crypto and US equity catalysts for the next week, separating facts from market opinion." },
    { title: "Strategy research", body: "Design a PAPER-first BTC research strategy and state its assumptions, risks, and backtest requirements first." },
  ];
  const latestAssistantId = [...messages].reverse().find((message) => message.role === "assistant" && message.status === "completed")?.id;
  const choosePrompt = (value: string) => {
    setInput(value);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  };

  return (
    /* The width contract lives here, not in the page wrapper.
       `/chat` wrapped this component in `IntelligenceShell` (max-width 1180px)
       while `/chat/[conversationId]` rendered it bare, so the same conversation
       changed text-column width when the route changed — and on a wide screen
       the bare route let content span the full viewport. Constraining the
       component itself means both routes agree by construction. */
    <OceanShell locale={locale} variant="agent" className="mx-auto h-[calc(100dvh-7rem)] min-h-[620px] w-full max-w-[1180px] rounded-2xl">
      <div className={`grid h-full min-h-[620px] grid-cols-1 overflow-hidden border border-border-pg bg-bg-panel ${historyCollapsed ? "lg:grid-cols-[44px_minmax(0,1fr)]" : "lg:grid-cols-[244px_minmax(0,1fr)]"}`}>
      {/* A backdrop is only rendered on small screens, where the history aside
          becomes a drawer. Without it the drawer would cover the transcript
          with no visible way back. */}
      {mobileHistoryOpen ? (
        <button
          type="button"
          aria-label={zh ? "关闭历史对话" : "Close conversation history"}
          onClick={closeMobileHistory}
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
        />
      ) : null}
      {historyCollapsed ? (
        <aside className="hidden border-r border-border-pg bg-bg-app lg:flex lg:flex-col lg:items-center lg:py-3">
          <button type="button" onClick={() => setHistoryCollapsed(false)} className="grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong rounded-lg" aria-label={zh ? "展开历史对话" : "Expand conversation history"}><PanelLeftOpen className="h-4 w-4" /></button>
        </aside>
      ) : (
      <aside
        ref={historyPanelRef}
        aria-label={zh ? "历史对话" : "Conversation history"}
        className={`${mobileHistoryOpen ? "flex" : "hidden"} fixed inset-y-3 left-3 z-50 w-80 max-w-[85vw] flex-col rounded-xl border border-border-pg bg-bg-panel shadow-2xl lg:static lg:z-auto lg:w-auto lg:max-w-none lg:rounded-none lg:border-0 lg:border-r lg:border-b-0 lg:bg-bg-app lg:shadow-none lg:flex`}
      >
        <div className="flex items-center justify-between border-b border-border-pg p-3">
          <div><div className="text-xs uppercase text-text-pg-dim">PureGamma Agent</div><div className="mt-1 text-xs text-text-pg-muted">{quota ? `${quota.remaining}/${quota.limit} ${zh ? "今日剩余" : "remaining"} · ${quota.credit_balance} Credits` : "-"}</div></div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setHistoryCollapsed(true)} className="hidden h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong rounded-lg lg:grid" aria-label={zh ? "收起历史对话" : "Collapse conversation history"}><PanelLeftClose className="h-4 w-4" /></button>
            <button type="button" onClick={closeMobileHistory} className="grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong rounded-lg lg:hidden" aria-label={zh ? "关闭历史对话" : "Close conversation history"}><X className="h-4 w-4" /></button>
            <button type="button" onClick={createNew} className="grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong rounded-lg" aria-label={zh ? "新会话" : "New conversation"}><MessageSquarePlus className="h-4 w-4" /></button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 lg:space-y-1">
          {conversations.map((conversation) => (
            <div key={conversation.id} className="group flex items-center">
              <button type="button" onClick={() => { router.push(withLocale(locale, `/chat/${conversation.id}`)); openConversation(conversation.id); setMobileHistoryOpen(false); }} className={`min-w-0 flex-1 border px-3 py-2 text-left text-sm  rounded-lg ${conversation.id === conversationId ? "border-border-pg-strong bg-bg-panel-muted" : "border-transparent text-text-pg-muted hover:border-border-pg"}`}>
                <div className="truncate font-medium">{conversation.title}</div>
                <div className="mt-1 text-xs text-text-pg-dim">{new Date(conversation.updated_at).toLocaleDateString(locale)}</div>
              </button>
              <button type="button" onClick={(event) => { event.stopPropagation(); void deleteConversation(conversation.id); }} aria-label={zh ? "删除会话" : "Delete conversation"} className="ml-0.5 grid h-9 w-8 shrink-0 place-items-center border border-transparent text-text-pg-dim hover:border-status-negative hover:text-status-negative lg:invisible lg:group-hover:visible rounded-lg"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
          {conversations.length === 0 ? <div className="px-3 py-4 text-center text-xs text-text-pg-dim">{zh ? "暂无历史对话" : "No conversation history"}</div> : null}
        </div>
        {conversations.length ? (
          <div className="border-t border-border-pg p-2">
            <button type="button" onClick={() => void deleteAll()} className="flex w-full items-center justify-center gap-2 border border-border-pg px-3 py-2 text-xs text-text-pg-dim hover:border-status-negative hover:text-status-negative transition rounded-lg" aria-label={zh ? "删除全部历史对话" : "Delete all conversation history"}>
              <Trash2 className="h-3.5 w-3.5" />
              <span>{zh ? "删除全部历史对话" : "Delete all history"}</span>
            </button>
          </div>
        ) : null}
      </aside>
      )}

      {/* `min-w-0` plus no `overflow-hidden` on the ancestors: the inner scroll
          container needs to be the element that clips, otherwise wide content
          (a long URL, a hash, a base64 blob) is silently truncated here with no
          ellipsis and no scrollbar. */}
      <section className="flex min-h-0 min-w-0 flex-col">
        <div ref={scrollRef} onScroll={(event) => { const target = event.currentTarget; followRef.current = target.scrollHeight - target.scrollTop - target.clientHeight < 120; }} className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          {loading ? <div className="grid min-h-64 place-items-center"><Loader2 className="h-5 w-5 animate-spin" /></div> : null}
          {!loading && messages.length === 0 ? <div className="mx-auto flex min-h-[55vh] max-w-3xl flex-col justify-center">
            <div className="max-w-2xl"><div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-text-pg-dim"><Compass className="h-4 w-4" />PureGamma Research Agent</div><h1 className="mt-4 text-2xl font-semibold leading-tight md:text-3xl">{zh ? "说出你正在判断的问题，其余交给 Agent。" : "State the decision you are working through. The Agent handles the rest."}</h1><p className="mt-3 max-w-xl text-sm leading-6 text-text-pg-muted">{zh ? "Agent 会理解目标、选择合适的 Skill、检查事实证据，并明确告诉你未知与风险。无需先选择工具。" : "The Agent understands the goal, selects authorized Skills, checks evidence, and makes uncertainty explicit. No tool setup required."}</p></div>
            <div className="mt-7 grid gap-2 sm:grid-cols-2">{starterPrompts.map((item) => <button key={item.title} type="button" onClick={() => choosePrompt(item.body)} className="group border border-border-pg bg-bg-app p-3 text-left transition hover:border-border-pg-strong hover:bg-bg-panel-muted rounded-lg"><span className="text-sm font-medium">{item.title}</span><span className="mt-1.5 block text-xs leading-5 text-text-pg-dim">{item.body}</span><span className="mt-3 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-text-pg-muted"><Target className="h-3 w-3" />{zh ? "作为目标使用" : "Use as goal"}</span></button>)}</div>
          </div> : null}
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((message) => <div key={message.id} className={message.role === "user" ? "ml-auto max-w-[min(85%,42rem)] break-words rounded-lg border border-border-pg-strong bg-bg-panel-muted p-3 text-sm" : "min-w-0 max-w-full overflow-x-auto border-l border-border-pg pl-4"}>
              {message.role === "assistant" ? <><div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-text-pg-dim"><span>{bylineModelLabel(message.model, modelCopy, defaultModelName, modelLabels)}</span>{message.context?.runtime?.intent ? <span className="border border-border-pg px-1.5 py-0.5 normal-case rounded-lg">{message.context.runtime.intent.replaceAll("_", " ")}</span> : null}{message.context?.evidence ? <span className={`inline-flex items-center gap-1 border px-1.5 py-0.5 normal-case rounded-lg ${message.context.evidence.sufficient ? "border-border-pg text-text-pg-muted" : "border-status-warning text-status-warning"}`}><SearchCheck className="h-3 w-3" />{zh ? "证据" : "Evidence"} · {message.context.evidence.sufficient ? (zh ? "通过" : "met") : (zh ? "缺口" : "gaps")}</span> : null}{message.sources.length ? <span className="inline-flex items-center gap-1 border border-border-pg px-1.5 py-0.5 normal-case rounded-lg"><Database className="h-3 w-3" />{zh ? "数据" : "Data"} · {message.sources.length} {zh ? "来源" : "sources"}</span> : null}</div><ReportMarkdown content={message.content || (message.status === "streaming" ? (zh ? "正在分析..." : "Analyzing...") : "")} locale={locale} /></> : <><p className="whitespace-pre-wrap leading-6">{message.content}</p>{message.context ? <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border-pg pt-2 text-[10px] text-text-pg-dim">{message.context.data_sources?.map((item) => <span key={item} className="border border-border-pg px-1.5 py-0.5 rounded-lg">{item}</span>)}{message.context.skills?.map((item) => typeof item === "string" ? <span key={item} className="border border-border-pg px-1.5 py-0.5 rounded-lg">{item.replaceAll("_", " ")}</span> : null)}{message.context.attachments?.length ? <AttachmentCards files={message.context.attachments} locale={locale} /> : null}</div> : null}</>}
              {message.status === "failed" ? <div className="mt-3 border border-status-negative p-3 text-sm text-status-negative rounded-lg"><p>{message.error_message}</p><button type="button" onClick={() => { setInput([...messages].reverse().find((item) => item.role === "user" && item.created_at <= message.created_at)?.content || ""); }} className="mt-2 inline-flex items-center gap-2 border border-border-pg px-2 py-1 rounded-lg"><RefreshCw className="h-3.5 w-3.5" />{zh ? "重试" : "Retry"}</button></div> : null}
              {message.role === "assistant" && message.status === "completed" && message.credits_used != null ? <div className="mt-3 text-right text-[10px] text-text-pg-dim">{zh ? "实际消耗" : "Actual cost"}: {message.credits_used} Credits</div> : null}
              {message.role === "assistant" && message.credits_refunded ? <div className="mt-3 text-right text-[10px] text-text-pg-dim">{zh ? "Credits 已退款" : "Credits refunded"}</div> : null}
              {message.role === "assistant" && message.context?.evidence ? <div className={`mt-3 flex flex-wrap items-center gap-2 border px-2.5 py-2 text-[11px]  rounded-lg ${message.context.evidence.sufficient ? "border-border-pg text-text-pg-muted" : "border-status-warning text-status-warning"}`}><SearchCheck className="h-3.5 w-3.5" /><span>{message.context.evidence.sufficient ? (zh ? "证据检查通过" : "Evidence requirements met") : (zh ? `证据不完整：${message.context.evidence.missing.join(", ")}` : `Evidence incomplete: ${message.context.evidence.missing.join(", ")}`)}</span><span className="ml-auto text-text-pg-dim">{message.context.evidence.source_count} {zh ? "条来源" : "sources"}</span></div> : null}
              {message.role === "assistant" && message.sources.length ? <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[10px] text-text-pg-dim"><span className="font-semibold">{zh ? "来源" : "Sources"}:</span>{message.sources.map((source) => source.url ? <a href={source.url} target="_blank" rel="noreferrer" key={`${message.id}-${source.citation_index}`} className="max-w-[190px] truncate border border-border-pg px-1.5 py-0.5 hover:border-border-pg-strong rounded-lg">[{source.citation_index}] {source.title}</a> : <span key={`${message.id}-${source.citation_index}`} className="max-w-[190px] truncate border border-border-pg px-1.5 py-0.5 rounded-lg">[{source.citation_index}] {source.title}</span>)}</div> : null}
              {message.id === latestAssistantId && message.context?.runtime?.next_actions?.length ? <div className="mt-4 flex flex-wrap gap-2">{message.context.runtime.next_actions.slice(0, 3).map((action) => <button key={action} type="button" onClick={() => choosePrompt(nextActionPrompt(action, zh))} className="inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg"><CheckCircle2 className="h-3 w-3" />{nextActionLabel(action, zh)}</button>)}</div> : null}
              {message.id === latestAssistantId && message.status === "completed" ? (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-border-pg pt-3">
                  <Link href={withLocale(locale, "/research")} className="inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg"><FlaskConical className="h-3 w-3" />{zh ? "生成交易研究" : "Generate trading research"}</Link>
                  <Link href={withLocale(locale, "/strategies")} className="inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg"><Target className="h-3 w-3" />{zh ? "生成策略草案" : "Draft a strategy"}</Link>
                  <Link href={withLocale(locale, "/trading/risk")} className="inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg"><ShieldCheck className="h-3 w-3" />{zh ? "进入交易安全页" : "Trading safety"}</Link>
                </div>
              ) : null}
            </div>)}
            {busy && runtimePlan ? <div className="flex flex-wrap items-center gap-2 border border-border-pg bg-bg-app px-3 py-2 text-xs text-text-pg-muted rounded-lg"><Target className="h-3.5 w-3.5" /><span>{zh ? "已理解" : "Understood"}: {runtimePlan.intent.replaceAll("_", " ")}</span>{runtimePlan.assets.length ? <span className="text-text-pg-dim">· {runtimePlan.assets.join(", ")}</span> : null}{evidenceStatus ? <span className={evidenceStatus.sufficient ? "ml-auto text-text-pg-muted" : "ml-auto text-status-warning"}>{evidenceStatus.sufficient ? (zh ? "证据已就绪" : "Evidence ready") : (zh ? "证据存在缺口" : "Evidence gaps found")}</span> : <span className="ml-auto text-text-pg-dim">{zh ? "正在构建证据包" : "Building evidence pack"}</span>}</div> : null}
            <AgentStageIndicator stage={stage} locale={locale} />
            {toolStatus.length ? <div className="flex flex-wrap gap-2">{toolStatus.map((item) => <span key={item.id} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs text-text-pg-muted rounded-lg"><Wrench className="h-3 w-3" />{item.tool} · {item.status}</span>)}</div> : null}
            {toolResults.map((result, index) => <StrategyToolResult key={`${result.tool}-${index}`} result={result} locale={locale} />)}
          </div>
        </div>
        <div className="shrink-0 border-t border-border-pg bg-bg-app p-3 md:p-4">
          <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2 lg:hidden">
            <button ref={historyTriggerRef} type="button" onClick={() => setMobileHistoryOpen(true)} aria-label={zh ? "历史对话" : "Conversation history"} aria-expanded={mobileHistoryOpen} data-testid="chat-history-trigger" className="flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm hover:bg-[var(--pg-surface-hover)]"><PanelLeftOpen className="h-4 w-4" />{zh ? "历史" : "History"}</button>
            <button type="button" onClick={createNew} aria-label={zh ? "新会话" : "New conversation"} data-testid="chat-new-trigger" className="grid h-10 w-10 place-items-center rounded-lg hover:bg-[var(--pg-surface-hover)]"><MessageSquarePlus className="h-4 w-4" /></button>
          </div>
          {approval ? <div role="alert" className="mx-auto mb-3 max-w-3xl rounded-lg border border-[var(--pg-border-default)] bg-[var(--pg-surface-2)] p-3" data-testid="tool-approval">
            <p className="text-sm font-medium">{zh ? "此操作需要你的确认" : "This action needs your approval"}</p>
            <p className="mt-1 break-words text-sm">{approval.tool.replaceAll("_", " ")}</p>
            <details className="mt-2 text-xs"><summary>{zh ? "查看参数" : "View arguments"}</summary><pre className="max-h-40 overflow-auto whitespace-pre-wrap">{JSON.stringify(approval.arguments, null, 2)}</pre></details>
            <div className="mt-3 flex gap-2">{(["denied", "approved"] as const).map(decision => <button key={decision} type="button" disabled={approving} className="min-h-10 rounded-md border border-[var(--pg-border-default)] px-4 text-sm" onClick={async () => { setApproving(true); try { await approveAgentTool(approval.toolCallId, decision); setApproval(null); } catch { setFailure({kind: "generic", message: zh ? "确认已过期或无法提交，请刷新会话。" : "Approval expired or could not be submitted. Refresh the conversation."}); } finally { setApproving(false); } }}>{decision === "approved" ? (zh ? "允许此次操作" : "Allow once") : (zh ? "拒绝" : "Deny")}</button>)}</div>
          </div> : null}
          <ChatWorkspaceComposer locale={locale} input={input} onInput={setInput} busy={busy} onSend={() => void send()} onStop={() => void stop()} attachments={attachments} onAttachments={setAttachments} permission={permission} onUploading={setUploading}
            onPermission={async (mode, acknowledged) => { if (conversationId) await setAgentPermission(conversationId, mode, acknowledged); setPermission(mode); }}
            researchMode={researchMode} onResearch={setResearchMode} onTextarea={node => { composerRef.current = node; }}
            modelControl={<select id="agent-model" aria-label={zh ? "模型" : "Model"} value={selectedModel} onChange={event => setSelectedModel(event.target.value)} disabled={busy} className="min-h-10 max-w-[220px] rounded-md bg-transparent text-xs text-text-pg focus-visible:ring-2">{models.map(model => <option key={model.id} value={model.id} disabled={!model.available}>{agentModelLabel(model, modelCopy, defaultModelName)}</option>)}</select>}
            settings={<ContextControls locale={locale} plugins={plugins} pluginCounts={pluginCounts} customPrompt={customPrompt} attachments={[]} onPrompt={setCustomPrompt} onRemoveFile={() => undefined} />} />
          {input.trim() && creditQuote && !creditQuote.unavailable ? <p className="mx-auto mt-2 max-w-3xl text-right text-xs text-text-pg-muted">{zh ? "预计" : "Estimated"} {estimatedCredits} Credits</p> : null}
          {failure ? (
            <div className="mx-auto mt-2 max-w-3xl border border-status-negative px-3 py-2 text-xs text-status-negative rounded-lg" role="alert" data-testid="chat-error">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1">{failure.message}</span>
                {failure.reference ? <span className="font-mono text-[10px] text-text-pg-dim" data-testid="chat-error-reference">{modelCopy.errors.reference}: {failure.reference}</span> : null}
                <button type="button" onClick={() => setFailure(null)} className="border border-border-pg px-2 py-1 text-[10px] text-text-pg-muted rounded-lg">{zh ? "关闭" : "Dismiss"}</button>
              </div>
              {/* Billing line states only what the backend settled: a refund is
                  asserted from `credits_refunded`, never from the error type. */}
              <p className="mt-1.5 text-[10px] text-text-pg-muted" data-testid="chat-error-billing" data-billing={failure.billing}>
                {billingNotice(locale, failure.billing)}
                {failure.billing === "unknown" ? <> · <Link href={withLocale(locale, "/gateway")} className="underline decoration-dotted underline-offset-2">{modelCopy.errors.usageLink}</Link></> : null}
              </p>
            </div>
          ) : null}
        </div>
      </section>
      </div>
    </OceanShell>
  );
}





