"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Archive, ArchiveRestore, CheckCircle2, Compass, Database, FlaskConical, Loader2, MessageSquarePlus, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, SearchCheck, ShieldCheck, Target, Trash2, WifiOff, X } from "lucide-react";
import { ChatWorkspaceComposer, AttachmentCards } from "@/components/chat-workspace-composer";
import { setAgentPermission, approveAgentTool, archiveAgentConversation, type AgentPermissionMode } from "@/lib/api";
import { ToolTimeline } from "@/components/agent/tool-timeline";
import { ToolApprovalCard, type PendingToolApproval } from "@/components/agent/tool-approval-card";
import { EvidenceInspector } from "@/components/agent/evidence-inspector";
import { applyToolEvent, isAlreadyApplied, isForeignRun, linkCitations, newClientRequestId, type ToolStep } from "@/lib/agent-run-events";
import { ReportMarkdown } from "@/components/puregamma";
import { ContextControls, nextActionLabel, nextActionPrompt, StrategyToolResult } from "@/components/chat-panels";
import { AgentStageIndicator, nextAgentStage, type AgentStage } from "@/components/ocean/agent-stage-indicator";
import { OceanShell } from "@/components/ocean/ocean-shell";
import { type Locale, withLocale } from "@/i18n/routing";
import { AgentAttachment, AgentCapabilities, AgentConversation, AgentEvidenceSummary, AgentMessage, AgentModelOption, AgentRuntimePlan, AgentPluginEntry, AgentSource, SkillSummary, cancelAgentRun, createAgentConversation, deleteAgentConversation, deleteAllAgentConversations, getAgentCapabilities, getAgentConversation, getAgentConversations, getAgentQuota, getAgentQuote, getAgentRunEvents, getGatewayCatalog, getMe, streamAgentMessage } from "@/lib/api";
import { billingNotice, describeChatFailure, type ChatFailure } from "@/lib/chat-errors";
import { FLASH_ALIAS_ID, FLASH_MODEL_ID, flashAvailability, platformDefaultModelName } from "@/lib/model-catalog";
import { getMessageNamespace } from "@/lib/translations";
import { publishCreditBalance } from "@/lib/user-state";

/** localStorage key for the desktop history column's collapsed state. */
const HISTORY_COLLAPSED_KEY = "pg:chat-history-collapsed";

/**
 * The Agent's `default` selection is a routing sentinel, not a model id: the
 * backend resolves it to the platform model. The request body must keep sending
 * `default`, but the user should read the model that will actually answer.
 *
 * `catalogName` is the catalog's own `display_name` for the platform default
 * model, so the label follows the deployment instead of a literal in this file.
 * The i18n string is only a fallback for when the catalog is unreachable.
 */
function agentModelLabel(model: AgentModelOption, copy: ModelUpgradeCopy, catalogName: string | null, zh: boolean) {
  const name = model.id === "default" ? catalogName || copy.chat.badgeLive : model.display_name;
  const provider = providerLabel(model.provider);
  // Server display names may already carry the provider ("GPT-6 Sol · OpenAI").
  const providerPart = provider && !name.toLowerCase().includes(provider.toLowerCase()) ? ` · ${provider}` : "";
  return `${name}${providerPart}${agentModelSuffix(model, zh)}${agentModelEstimate(model, zh)}`;
}

const PROVIDER_LABELS: Record<string, string> = { openai: "OpenAI", deepseek: "DeepSeek", moonshot: "Moonshot", kimi: "Kimi", glm: "GLM", typesafe: "TypeSafe" };

function providerLabel(provider: string | null | undefined) {
  if (!provider || provider === "default" || provider === "mock") return "";
  return PROVIDER_LABELS[provider.toLowerCase()] ?? provider;
}

function agentModelSuffix(model: AgentModelOption, zh: boolean) {
  if (model.id === "default") return zh ? " · 平台默认路由" : " · platform default route";
  if (model.available) return "";
  if (model.reason === "pricing_not_configured") return zh ? " · 未配置计价" : " · pricing not configured";
  if (model.reason === "plan_required") return zh ? " · 需要 Max/Enterprise" : " · Max/Enterprise required";
  return zh ? " · 当前不可用" : " · unavailable";
}

/**
 * The server's typical-turn range, from the same rates billing uses. It is a
 * menu hint only: the composer's estimate line remains the quote for the
 * actual message, and the settled amount is what is charged.
 */
function agentModelEstimate(model: AgentModelOption, zh: boolean) {
  const estimate = model.estimate;
  if (!estimate || !Number.isFinite(estimate.min) || !Number.isFinite(estimate.max)) return "";
  const range = estimate.min === estimate.max ? `${estimate.min}` : `${estimate.min}–${estimate.max}`;
  return zh ? ` · 每轮约 ${range} Credits` : ` · ~${range} Credits/turn`;
}

/** Why the models missing from the menu are missing, counted by server reason. */
function lockedModelNote(models: AgentModelOption[], zh: boolean) {
  const locked = models.filter((model) => !model.available && model.category !== "evaluation");
  if (!locked.length) return undefined;
  const plan = locked.filter((model) => model.reason === "plan_required").length;
  const pricing = locked.filter((model) => model.reason === "pricing_not_configured").length;
  const other = locked.length - plan - pricing;
  const parts = zh
    ? [plan ? `${plan} 个需要升级套餐` : "", pricing ? `${pricing} 个尚未配置计价` : "", other ? `${other} 个当前不可用` : ""]
    : [plan ? `${plan} need a plan upgrade` : "", pricing ? `${pricing} have no pricing configured` : "", other ? `${other} unavailable` : ""];
  const detail = parts.filter(Boolean).join(zh ? "，" : ", ");
  return zh ? `另有 ${locked.length} 个模型不在列表中：${detail}` : `${locked.length} more model${locked.length === 1 ? "" : "s"} not listed: ${detail}`;
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
  // Never invent a product name for an id the server's catalog does not list:
  // the recorded id is the honest label.
  return id;
}

export function AgentChat({ locale, initialConversationId }: { locale: Locale; initialConversationId?: string }) {
  const router = useRouter();
  const zh = locale === "zh";
  const modelCopy = getMessageNamespace(locale, "model-upgrade");
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [conversationId, setConversationIdState] = useState(initialConversationId || "");
  const conversationIdRef = useRef(initialConversationId || "");
  const setConversationId = (value: string) => { conversationIdRef.current = value; setConversationIdState(value); };
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ChatFailure | null>(null);
  // Set when a lost response body was replayed from the durable transcript.
  const [recovered, setRecovered] = useState(false);
  // Tool steps of the current (or reattached) run, projected from server events.
  const [toolSteps, setToolSteps] = useState<ToolStep[]>([]);
  /** "recovering" while the stream is down and the durable log is being read. */
  const [connection, setConnection] = useState<"recovering" | null>(null);
  /** Set when a reload found this conversation's run still in progress. */
  const [observing, setObserving] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [inspector, setInspector] = useState<{ messageId: string; focus?: number } | null>(null);
  /** The last attempt that failed before any response; retried with the SAME request id. */
  const [unsentAttempt, setUnsentAttempt] = useState<{ content: string; key: string } | null>(null);
  const [toolResults, setToolResults] = useState<Array<{ tool: string; data: Record<string, unknown> }>>([]);
  const [dreamProgress, setDreamProgress] = useState<{ status: string; evaluations?: number } | null>(null);
  const [stage, setStage] = useState<AgentStage | null>(null);
  const [quota, setQuota] = useState<{ remaining: number | null; limit: number | null; credit_balance: number } | null>(null);
  const [capabilities, setCapabilities] = useState<AgentCapabilities | null>(null);
  const [models, setModels] = useState<AgentModelOption[]>([]);
  // Built-in capability inventory, straight from `/agent/capabilities`.
  const [plugins, setPlugins] = useState<AgentPluginEntry[]>([]);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
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
  const [approval, setApproval] = useState<PendingToolApproval | null>(null);
  const [approving, setApproving] = useState(false);
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const [runtimePlan, setRuntimePlan] = useState<AgentRuntimePlan | null>(null);
  const [evidenceStatus, setEvidenceStatus] = useState<AgentEvidenceSummary | null>(null);
  const [historyCollapsed, setHistoryCollapsedState] = useState(false);
  // Desktop collapse is a layout preference: it survives reloads and route
  // changes. Read after mount so server and first client render agree.
  useEffect(() => {
    try { setHistoryCollapsedState(window.localStorage.getItem(HISTORY_COLLAPSED_KEY) === "1"); } catch { /* storage unavailable */ }
  }, []);
  const setHistoryCollapsed = (value: boolean) => {
    setHistoryCollapsedState(value);
    try { window.localStorage.setItem(HISTORY_COLLAPSED_KEY, value ? "1" : "0"); } catch { /* storage unavailable */ }
  };
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
        historyTriggerRef.current?.focus();
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
  // Highest durable sequence this client has applied. A reconnect asks for
  // everything after it, so the gap is replayed instead of guessed.
  const lastSeqRef = useRef(0);
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

  /** Bumped whenever the shown conversation changes, so a stale poll stops. */
  const viewTokenRef = useRef(0);

  const openConversation = async (id: string) => {
    if (busy || uploading) return;
    const token = ++viewTokenRef.current;
    const result = await getAgentConversation(id);
    if (token !== viewTokenRef.current) return;
    setApproval(result.pending_approvals?.[0] ?? null);
    setConversationId(id);
    setPermission(result.conversation.permission_mode || "workspace-write");
    setMessages(result.messages);
    setToolSteps([]);
    setToolResults([]);
    setDreamProgress(null);
    setRuntimePlan(null);
    setEvidenceStatus(null);
    setFailure(null);
    setStopped(false);
    setInspector(null);
    setUnsentAttempt(null);
    // A run still in progress (another tab, or a reload mid-answer) is shown
    // from the server's event log instead of being presented as finished.
    if (result.active_run_id) void observeRun(id, result.active_run_id, token);
  };

  /** Apply one durable event from the replay log to the transcript view. */
  const applyReplayed = (type: string, data: Record<string, unknown>) => {
    setToolSteps((current) => applyToolEvent(current, type, data));
    if (type === "approval.required") {
      setApproval({ toolCallId: String(data.toolCallId), tool: String(data.tool), arguments: (data.arguments as Record<string, unknown>) || {}, expiresAt: data.expiresAt ? String(data.expiresAt) : undefined, permissionMode: data.permissionMode ? String(data.permissionMode) : undefined });
    } else if (type === "tool.completed") {
      setApproval((current) => (current?.toolCallId === String(data.toolCallId) ? null : current));
    } else if (type === "plan.ready") {
      setStage((current) => nextAgentStage(current, "selecting"));
    } else if (type === "tool.started") {
      setStage((current) => nextAgentStage(current, "collecting"));
    } else if (type === "evidence.ready") {
      setStage((current) => nextAgentStage(current, "validating"));
      setEvidenceStatus(data as unknown as AgentEvidenceSummary);
    }
  };

  /**
   * Follow a run through its durable event log until the server says it has
   * finished, then load the persisted answer. Network errors keep waiting:
   * a failed poll is not a failed run. `token` stops the loop when the user
   * opens another conversation.
   */
  const followRunLog = async (conversationId: string, runId: string, token: number, deadlineMs = 45_000): Promise<string | null> => {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline && token === viewTokenRef.current) {
      try {
        const page = await getAgentRunEvents(runId, lastSeqRef.current);
        for (const event of page.events || []) {
          const data = { ...(event.data || {}), seq: event.seq };
          if (isAlreadyApplied(data, lastSeqRef.current)) continue;
          lastSeqRef.current = event.seq;
          applyReplayed(event.type, data);
        }
        if (page.lastSeq > lastSeqRef.current) lastSeqRef.current = page.lastSeq;
        if (page.status !== "pending" && page.status !== "running") {
          const snapshot = await getAgentConversation(conversationId);
          if (token === viewTokenRef.current) setMessages(snapshot.messages);
          return page.status;
        }
        if (page.truncated) continue;
      } catch {
        // Offline or a proxy hiccup: keep waiting rather than declaring failure.
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2_500));
    }
    return null;
  };

  const observeRun = async (conversationId: string, runId: string, token: number) => {
    activeRunRef.current = runId;
    lastSeqRef.current = 0;
    setObserving(true);
    setStage("understanding");
    try {
      await followRunLog(conversationId, runId, token, 10 * 60_000);
    } finally {
      if (token === viewTokenRef.current) {
        setObserving(false);
        setStage(null);
        activeRunRef.current = "";
      }
    }
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
        // The built-in capability inventory was fetched but never shown.
        setPlugins(Array.isArray(access.plugins) ? access.plugins : []);
        setSkills(Array.isArray(access.skills) ? access.skills : []);
        setPluginCounts(access.plugin_counts ?? null);
        const target = initialConversationId || rows.find((row) => !row.archived_at)?.id;
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
  }, [messages, toolSteps]);

  // A prompt handed over from another page (`/chat?prompt=` from the command
  // surface, `?topic=` from Market Wire) pre-fills the composer. It is never
  // sent automatically: the user reads it first.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const handed = (params.get("prompt") || params.get("topic") || "").trim();
    if (handed) setInput((current) => current || handed.slice(0, 4000));
  }, []);

  const createNew = async () => {
    if (busy || uploading) return;
    setPermission("workspace-write");
    setApproval(null);
    setMobileHistoryOpen(false);
    try {
      const result = await createAgentConversation();
      viewTokenRef.current += 1;
      setConversations((current) => [result.conversation, ...current]);
      setConversationId(result.conversation.id);
      setMessages([]);
      setToolSteps([]);
      router.push(withLocale(locale, `/chat/${result.conversation.id}`));
    } catch (reason) {
      setFailure(describeChatFailure(locale, reason));
    }
  };

  const historyFailed = () => setHistoryError(zh ? "操作未完成，历史已恢复为服务端状态。" : "That change did not go through; the list shows what the server has.");

  const deleteConversation = async (id: string) => {
    const before = conversations;
    setHistoryError("");
    setConversations((current) => current.filter((conversation) => conversation.id !== id));
    try {
      await deleteAgentConversation(id);
    } catch {
      // Put the row back instead of pretending it is gone.
      setConversations(before);
      historyFailed();
      return;
    }
    if (conversationId === id) {
      const remaining = before.filter((conversation) => conversation.id !== id && !conversation.archived_at);
      if (remaining.length) {
        router.push(withLocale(locale, `/chat/${remaining[0].id}`));
        void openConversation(remaining[0].id);
      } else {
        viewTokenRef.current += 1;
        setConversationId("");
        setMessages([]);
        router.push(withLocale(locale, "/chat"));
      }
    }
  };

  const setArchived = async (id: string, archived: boolean) => {
    const before = conversations;
    setHistoryError("");
    setConversations((current) => current.map((conversation) => (conversation.id === id ? { ...conversation, archived_at: archived ? new Date().toISOString() : null } : conversation)));
    try {
      const result = await archiveAgentConversation(id, archived);
      setConversations((current) => current.map((conversation) => (conversation.id === id ? result.conversation : conversation)));
    } catch {
      setConversations(before);
      historyFailed();
    }
  };

  const deleteAll = async () => {
    const before = conversations;
    setHistoryError("");
    setConversations([]);
    try {
      await deleteAllAgentConversations();
    } catch {
      setConversations(before);
      historyFailed();
      return;
    }
    viewTokenRef.current += 1;
    setConversationId("");
    setMessages([]);
    router.push(withLocale(locale, "/chat"));
  };

  const ensureConversation = async () => {
    if (conversationId) return conversationId;
    const result = await createAgentConversation();
    setConversationId(result.conversation.id);
    setConversations((current) => [result.conversation, ...current]);
    window.history.replaceState(null, "", withLocale(locale, `/chat/${result.conversation.id}`));
    return result.conversation.id;
  };

  const send = async (event?: FormEvent, retry?: { content: string; key: string }) => {
    event?.preventDefault();
    // A file the user removed is still shown (so the conversation stays honest)
    // but must never be sent: its bytes are gone.
    const outgoing = retry ? [] : attachments.filter((file) => !file.removed);
    const content = retry?.content || input.trim() || (outgoing.length ? (zh ? "请分析所附文件。" : "Please analyze the attached files.") : "");
    // A ref, not just the `busy` state: two submissions in the same tick would
    // both read the pre-update state and start two runs.
    if (!content || busy || observing || uploading || sendingRef.current) return;
    // One id per attempt. A retry of an attempt that never got an answer
    // reuses it, so the server can say "already received" instead of starting
    // (and charging for) a second run.
    const requestKey = retry?.key || newClientRequestId();
    sendingRef.current = true;
    setBusy(true);
    setFailure(null);
    setUnsentAttempt(null);
    setStopped(false);
    setToolSteps([]);
    setToolResults([]);
    setDreamProgress(null);
    setRuntimePlan(null);
    setEvidenceStatus(null);
    setStage(null);
    setInspector(null);
    followRef.current = true;
    const token = viewTokenRef.current;
    // Declared outside the try: the recovery path in `catch` needs the
    // conversation even when the request itself never produced a stream.
    let conversationId = "";
    let assistantId = "";
    let assistantContent = "";
    let completed = false;
    let streamStarted = false;
    /** True once an SSE event reported the run's own failure and its billing. */
    let failureReported = false;
    const localId = `local-${Date.now()}`;
    try {
      const existed = Boolean(conversationId || (typeof window !== "undefined" && conversationIdRef.current));
      const id = await ensureConversation();
      conversationId = id;
      // The mode is persisted when the user changes it; only a conversation
      // created just now still needs the choice made before it existed.
      if (!existed && permission !== "workspace-write") await setAgentPermission(id, permission);
      setInput("");
      const now = new Date().toISOString();
      // Capabilities are built-in plugins now: the Agent picks its own sources and
      // tools from the goal. The request carries no skill selection at all.
      const context = { research_mode: researchMode, data_sources: researchMode ? dataSources : [], custom_prompt: researchMode ? customPrompt : "", attachments: outgoing, model: selectedModel, permission_mode: permission };
      setMessages((current) => [...current, { id: localId, conversation_id: id, role: "user", content, status: "completed", input_tokens: 0, output_tokens: 0, created_at: now, context, sources: [] }]);
      const controller = new AbortController();
      controllerRef.current = controller;
      lastSeqRef.current = 0;
      setRecovered(false);
      await streamAgentMessage(id, content, locale, controller.signal, ({ event: eventName, data }) => {
        streamStarted = true;
        // Server events are the truth: a frame at or below the cursor was
        // already applied (re-delivery), and a frame for another run is stale.
        if (isAlreadyApplied(data, lastSeqRef.current) || isForeignRun(data, activeRunRef.current)) return;
        if (typeof data.seq === "number") lastSeqRef.current = Number(data.seq);
        setToolSteps((current) => applyToolEvent(current, eventName, data));
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
        } else if (eventName === "tool.completed") {
          setApproval(current => current?.toolCallId === String(data.toolCallId) ? null : current);
          if (data.data && typeof data.data === "object") setToolResults((current) => [...current, { tool: String(data.tool), data: data.data as Record<string, unknown> }]);
        } else if (eventName === "dream.started") {
          setStage((current) => nextAgentStage(current, "collecting"));
          setDreamProgress({ status: "exploring" });
        } else if (eventName === "dream.completed") {
          const compute = data.compute && typeof data.compute === "object" ? data.compute as Record<string, unknown> : {};
          setDreamProgress({ status: String(data.status || "completed"), evaluations: Number(compute.evaluations || 0) });
        } else if (eventName === "citation") {
          const source: AgentSource = { provider: String(data.provider), title: String(data.title), url: data.url ? String(data.url) : null, published_at: data.publishedAt ? String(data.publishedAt) : null, source_timestamp: data.sourceTimestamp ? String(data.sourceTimestamp) : null, fetched_at: String(data.fetchedAt), citation_index: Number(data.index) };
          setMessages((current) => current.map((message) => message.id === assistantId && !message.sources.some((item) => item.citation_index === source.citation_index) ? { ...message, sources: [...message.sources, source] } : message));
        } else if (eventName === "evidence.ready") {
          setStage((current) => nextAgentStage(current, "validating"));
          setEvidenceStatus(data as unknown as AgentEvidenceSummary);
        } else if (eventName === "approval.required") {
          setApproval({ toolCallId: String(data.toolCallId), tool: String(data.tool), arguments: (data.arguments as Record<string, unknown>) || {}, expiresAt: data.expiresAt ? String(data.expiresAt) : undefined, permissionMode: data.permissionMode ? String(data.permissionMode) : undefined });
        } else if (eventName === "message.completed") {
          setStage(null);
          completed = true;
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "completed", model: String(data.model || message.model || ""), input_tokens: Number(data.inputTokens || 0), output_tokens: Number(data.outputTokens || 0), credits_used: Number(data.creditsUsed || 0), context: { data_sources: [], skills: [], custom_prompt: "", attachments: [], model: String(data.model || message.model || ""), evidence: data.evidence as AgentEvidenceSummary | undefined } } : message));
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
      }, context, requestKey);
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
        setFailure(describeChatFailure(locale, null, {
          kind: "empty_answer",
          refunded: settled?.credits_refunded === true,
          settled: settled?.credits_refunded === false,
        }));
      } else if (!failureReported && assistantId && !completed) {
        // The stream ended cleanly but never emitted `message.completed`: a
        // proxy cut the body without an error. Read what the server recorded.
        await recoverFromServer(id, token, assistantId);
      }
      await loadConversations();
      const refreshedQuota = await getAgentQuota();
      setQuota(refreshedQuota);
      publishCreditBalance(refreshedQuota.credit_balance);
    } catch (reason) {
      const failureInfo = reason as Error & { status?: number; code?: string; detail?: Record<string, unknown> };
      if (failureInfo.name === "AbortError") {
        // The user stopped the run; that is a normal outcome, not an error.
      } else if (failureInfo.status === 409 && failureInfo.code === "DUPLICATE_SUBMISSION" && conversationId) {
        // The server already has this exact attempt: follow that run instead
        // of starting another one.
        setMessages((current) => current.filter((message) => message.id !== localId));
        const runId = typeof failureInfo.detail?.runId === "string" ? failureInfo.detail.runId : "";
        if (runId) {
          activeRunRef.current = runId;
          setConnection("recovering");
          await followRunLog(conversationId, runId, token);
          setConnection(null);
        } else {
          setMessages((await getAgentConversation(conversationId)).messages);
        }
        setRecovered(true);
      } else if (streamStarted || assistantId) {
        // The response body died mid-stream. Show "reconnecting", not
        // "failed": read the server's record of this run before saying
        // anything about it.
        await recoverFromServer(conversationId, token, assistantId, reason);
      } else if (conversationId && !failureInfo.status) {
        // The request never produced a response (network, proxy, restart).
        // Whether the server received it is unknown, so ask the server.
        await recoverUnsent(conversationId, token, content, requestKey, localId, reason);
      } else {
        setMessages((current) => current.filter((message) => message.id !== localId));
        if (!retry) setInput(content);
        setFailure(describeChatFailure(locale, reason));
      }
    } finally {
      setApproval(null);
      setBusy(false);
      setStage(null);
      setConnection(null);
      activeRunRef.current = "";
      controllerRef.current = null;
      sendingRef.current = false;
    }
  };

  /**
   * The stream for a started run died. Mark the turn as reconnecting, follow
   * the durable log until the server reports the run's final status, and show
   * that status: a run the server completed is shown completed; a run it
   * recorded as interrupted or failed is shown with its recorded settlement.
   */
  const recoverFromServer = async (conversationId: string, token: number, assistantMessageId: string, reason?: unknown) => {
    if (!conversationId) return;
    setConnection("recovering");
    const deadline = Date.now() + 45_000;
    let snapshot: Awaited<ReturnType<typeof getAgentConversation>> | null = null;
    // Ask the conversation first: only a run the server still reports as
    // active is worth following; otherwise its outcome is already recorded.
    while (!snapshot && Date.now() < deadline && token === viewTokenRef.current) {
      try {
        snapshot = await getAgentConversation(conversationId);
      } catch {
        await new Promise((resolve) => window.setTimeout(resolve, 2_500));
      }
    }
    if (snapshot?.active_run_id) {
      activeRunRef.current = snapshot.active_run_id;
      await followRunLog(conversationId, snapshot.active_run_id, token, Math.max(5_000, deadline - Date.now()));
      try { snapshot = await getAgentConversation(conversationId); } catch { /* keep the last snapshot */ }
    }
    if (token !== viewTokenRef.current) return;
    if (snapshot) setMessages(snapshot.messages);
    const settled = snapshot?.messages.find((message) => message.id === assistantMessageId);
    if (settled?.status === "completed" && settled.content.trim()) {
      setRecovered(true);
      setFailure(null);
      return;
    }
    if (!settled) setMessages((current) => current.map((message) => message.id === assistantMessageId && message.status === "streaming" ? { ...message, status: "interrupted" } : message));
    // Billing is stated only from the stored settlement; without a record it
    // stays "check the usage record".
    setFailure(describeChatFailure(locale, reason ?? null, {
      kind: "stream_interrupted",
      refunded: settled?.credits_refunded === true,
      settled: settled?.credits_refunded === false,
    }));
  };

  /**
   * The request never got a response. Look for it on the server by its
   * request id: if it arrived, follow its run; if not, offer a retry that
   * reuses the same id, so a late arrival is still recognised as one turn.
   */
  const recoverUnsent = async (conversationId: string, token: number, content: string, requestKey: string, localId: string, reason: unknown) => {
    setConnection("recovering");
    try {
      const snapshot = await getAgentConversation(conversationId);
      const arrived = snapshot.messages.find((message) => message.role === "user" && (message.context as Record<string, unknown> | undefined)?.client_request_id === requestKey);
      if (arrived) {
        if (snapshot.active_run_id) {
          activeRunRef.current = snapshot.active_run_id;
          await followRunLog(conversationId, snapshot.active_run_id, token);
        } else {
          setMessages(snapshot.messages);
        }
        setRecovered(true);
        return;
      }
    } catch { /* still offline: fall through to an explicit, safe retry */ }
    if (token !== viewTokenRef.current) return;
    setMessages((current) => current.filter((message) => message.id !== localId));
    setUnsentAttempt({ content, key: requestKey });
    setFailure(describeChatFailure(locale, reason));
  };

  const stop = async () => {
    const runId = activeRunRef.current;
    if (runId) await cancelAgentRun(runId).catch(() => undefined);
    controllerRef.current?.abort();
    setBusy(false);
    setObserving(false);
    viewTokenRef.current += 1;
    setStopped(true);
    if (conversationId) {
      try {
        const refreshed = await getAgentConversation(conversationId);
        setMessages(refreshed.messages);
        setQuota(await getAgentQuota().catch(() => quota));
      } catch { /* keep current view when refresh fails */ }
    }
  };

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
    { title: "Dream-RSI 策略发现", body: "找一个 BTC 15m，最大回撤 < 12%，Sharpe > 1.8 的策略。" },
  ] : [
    { title: "BTC market now", body: "Use a fresh quote and traceable sources to assess BTC's current market regime, drivers, and risks." },
    { title: "My portfolio risk", body: "Review my portfolio concentration, major exposures, and the changes I should watch first." },
    { title: "This week's catalysts", body: "Map the most important crypto and US equity catalysts for the next week, separating facts from market opinion." },
    { title: "Dream-RSI discovery", body: "Find a BTC 15m strategy with max drawdown < 12% and Sharpe > 1.8." },
  ];
  const latestAssistantId = [...messages].reverse().find((message) => message.role === "assistant" && message.status === "completed")?.id;
  const choosePrompt = (value: string) => {
    setInput(value);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  };

  const usableModels = models.filter((model) => model.available && model.category !== "evaluation");
  const query = historyQuery.trim().toLowerCase();
  const visibleConversations = conversations.filter((conversation) => Boolean(conversation.archived_at) === showArchived && (!query || conversation.title.toLowerCase().includes(query)));
  const archivedCount = conversations.filter((conversation) => conversation.archived_at).length;
  const working = busy || observing;
  const inspectorMessage = inspector ? messages.find((message) => message.id === inspector.messageId) : undefined;

  /** Citation markers in an answer open the evidence inspector at that source. */
  const onTranscriptClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const anchor = (event.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#cite-"]');
    if (!anchor) return;
    event.preventDefault();
    const match = /^#cite-(.+)-(\d+)$/.exec(anchor.getAttribute("href") || "");
    if (match) openInspector({ messageId: match[1], focus: Number(match[2]) }, anchor);
  };
  /** Where focus goes back to when the inspector closes. */
  const inspectorReturnRef = useRef<{ element: HTMLElement | null; selector: string }>({ element: null, selector: "" });
  const openInspector = (target: { messageId: string; focus?: number }, opener: HTMLElement | null) => {
    // The markdown renderer may replace a citation's <a> on re-render, so the
    // way back is also kept as a selector.
    const href = opener?.getAttribute("href");
    inspectorReturnRef.current = { element: opener, selector: href ? `a[href="${href}"]` : `#message-${target.messageId} [data-testid="open-evidence"]` };
    setInspector(target);
  };
  const closeInspector = () => {
    setInspector(null);
    window.setTimeout(() => {
      const { element, selector } = inspectorReturnRef.current;
      const target = element?.isConnected ? element : selector ? document.querySelector<HTMLElement>(selector) : null;
      target?.focus();
    }, 0);
  };

  return (
    /* The width contract lives here, not in the page wrapper.
       `/chat` wrapped this component in `IntelligenceShell` (max-width 1180px)
       while `/chat/[conversationId]` rendered it bare, so the same conversation
       changed text-column width when the route changed — and on a wide screen
       the bare route let content span the full viewport. Constraining the
       component itself means both routes agree by construction. */
    <OceanShell locale={locale} variant="agent" className="mx-auto h-[calc(100dvh-7rem)] min-h-[480px] w-full max-w-[1180px] rounded-3xl bg-bg-panel shadow-panel">
      <div className={`grid h-full min-h-[480px] grid-cols-1 overflow-hidden bg-bg-panel ${historyCollapsed ? "lg:grid-cols-[44px_minmax(0,1fr)]" : "lg:grid-cols-[244px_minmax(0,1fr)]"}`}>
      {/* A backdrop is only rendered on small screens, where the history aside
          becomes a drawer. Without it the drawer would cover the transcript
          with no visible way back. */}
      {historyCollapsed ? (
        <aside className="hidden border-r border-border-pg bg-bg-panel-muted lg:flex lg:flex-col lg:items-center lg:py-3">
          <button type="button" onClick={() => setHistoryCollapsed(false)} className="grid h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong" aria-label={zh ? "展开历史对话" : "Expand conversation history"} aria-expanded={false}><PanelLeftOpen className="h-4 w-4" /></button>
        </aside>
      ) : null}
      {historyCollapsed ? null : (
        <aside id="chat-history-panel" aria-label={zh ? "历史对话" : "Conversation history"} className="hidden border-r border-border-pg bg-bg-panel-muted lg:flex lg:min-h-0 lg:flex-col">
        <div className="flex items-center justify-between border-b border-border-pg p-3">
          <div className="min-w-0"><div className="text-xs uppercase text-text-pg-dim">PureGamma Agent</div><div className="mt-1 truncate text-[11px] text-text-pg-dim" data-testid="chat-usage-summary">{quota ? `${quota.remaining}/${quota.limit} ${zh ? "今日剩余" : "left today"} · ${quota.credit_balance} Credits` : "-"}</div></div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setHistoryCollapsed(true)} className="hidden h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong lg:grid" aria-label={zh ? "收起历史对话" : "Collapse conversation history"} aria-expanded><PanelLeftClose className="h-4 w-4" /></button>
            <button type="button" onClick={closeMobileHistory} className="grid h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong lg:hidden" aria-label={zh ? "关闭历史对话" : "Close conversation history"}><X className="h-4 w-4" /></button>
            <button type="button" onClick={() => void createNew()} className="grid h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong" aria-label={zh ? "新会话" : "New conversation"}><MessageSquarePlus className="h-4 w-4" /></button>
          </div>
        </div>
        <div className="space-y-2 border-b border-border-pg p-2">
          <label className="flex items-center gap-2 rounded-lg bg-bg-panel px-2 focus-within:ring-2 focus-within:ring-[var(--pg-focus-ring)]">
            <Search className="h-3.5 w-3.5 shrink-0 text-text-pg-dim" aria-hidden />
            <span className="sr-only">{zh ? "搜索历史对话" : "Search conversations"}</span>
            <input type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder={zh ? "搜索标题" : "Search titles"} className="min-h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" data-testid="chat-history-search" />
          </label>
          <div className="flex gap-1 text-xs" role="group" aria-label={zh ? "历史筛选" : "History filter"}>
            <button type="button" aria-pressed={!showArchived} onClick={() => setShowArchived(false)} className={`min-h-8 flex-1 rounded-md px-2 ${!showArchived ? "bg-bg-panel text-text-pg" : "text-text-pg-muted hover:text-text-pg"}`}>{zh ? "进行中" : "Active"}</button>
            <button type="button" aria-pressed={showArchived} onClick={() => setShowArchived(true)} className={`min-h-8 flex-1 rounded-md px-2 ${showArchived ? "bg-bg-panel text-text-pg" : "text-text-pg-muted hover:text-text-pg"}`}>{zh ? `已归档 ${archivedCount}` : `Archived ${archivedCount}`}</button>
          </div>
        </div>
        {historyError ? <p role="alert" className="mx-2 mt-2 rounded-md px-2 py-1.5 text-xs text-status-negative">{historyError}</p> : null}
        <div className="flex-1 overflow-y-auto p-2 lg:space-y-1">
          {visibleConversations.map((conversation) => (
            <div key={conversation.id} className="group flex items-center">
              <button type="button" aria-current={conversation.id === conversationId ? "page" : undefined} onClick={() => { router.push(withLocale(locale, `/chat/${conversation.id}`)); void openConversation(conversation.id); if (mobileHistoryOpen) closeMobileHistory(); }} className={`min-w-0 flex-1 rounded-xl border px-3 py-2 text-left text-sm ${conversation.id === conversationId ? "border-border-pg bg-bg-panel shadow-card" : "border-transparent text-text-pg-muted hover:border-border-pg hover:bg-bg-panel"}`}>
                <div className="truncate font-medium">{conversation.title}</div>
                <div className="mt-1 text-xs text-text-pg-dim">{new Date(conversation.updated_at).toLocaleDateString(locale)}</div>
              </button>
              <div className="ml-0.5 flex shrink-0 lg:invisible lg:group-hover:visible lg:group-focus-within:visible">
                <button type="button" onClick={(event) => { event.stopPropagation(); void setArchived(conversation.id, !conversation.archived_at); }} aria-label={conversation.archived_at ? (zh ? `取消归档：${conversation.title}` : `Unarchive: ${conversation.title}`) : (zh ? `归档：${conversation.title}` : `Archive: ${conversation.title}`)} className="grid h-9 w-8 place-items-center rounded-lg border border-transparent text-text-pg-dim hover:border-border-pg hover:text-text-pg">{conversation.archived_at ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}</button>
                <button type="button" onClick={(event) => { event.stopPropagation(); void deleteConversation(conversation.id); }} aria-label={zh ? `删除会话：${conversation.title}` : `Delete conversation: ${conversation.title}`} className="grid h-9 w-8 place-items-center rounded-lg border border-transparent text-text-pg-dim hover:border-status-negative hover:text-status-negative"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
          ))}
          {visibleConversations.length === 0 ? <div className="px-3 py-4 text-center text-xs text-text-pg-dim">{query ? (zh ? "没有匹配的对话" : "No matching conversations") : showArchived ? (zh ? "没有已归档的对话" : "No archived conversations") : (zh ? "暂无历史对话" : "No conversation history")}</div> : null}
        </div>
        {conversations.length ? (
          <div className="border-t border-border-pg p-2">
            <button type="button" onClick={() => void deleteAll()} className="flex w-full items-center justify-center gap-2 rounded-lg border border-border-pg px-3 py-2 text-xs text-text-pg-dim transition-colors hover:border-status-negative hover:text-status-negative" aria-label={zh ? "删除全部历史对话" : "Delete all conversation history"}>
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
        <div ref={scrollRef} onClick={onTranscriptClick} onScroll={(event) => { const target = event.currentTarget; followRef.current = target.scrollHeight - target.scrollTop - target.clientHeight < 120; }} className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          {loading ? <div className="mx-auto max-w-3xl space-y-4" aria-busy="true" aria-label={zh ? "加载中" : "Loading"}><div className="h-4 w-1/3 animate-pulse rounded bg-[var(--pg-surface-2)] motion-reduce:animate-none" /><div className="h-24 animate-pulse rounded-xl bg-[var(--pg-surface-2)] motion-reduce:animate-none" /></div> : null}
          {!loading && messages.length === 0 ? <div className="mx-auto flex min-h-[55vh] max-w-3xl flex-col justify-center">
            <div className="max-w-2xl"><div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-text-pg-dim"><Compass className="h-4 w-4" />PureGamma Research Agent</div><h1 className="mt-4 text-2xl font-semibold leading-tight md:text-3xl">{zh ? "说出你正在判断的问题，其余交给 Agent。" : "State the decision you are working through. The Agent handles the rest."}</h1><p className="mt-3 max-w-xl text-sm leading-6 text-text-pg-muted">{zh ? "Agent 会理解目标、选择合适的 Skill、检查事实证据，并明确告诉你未知与风险。无需先选择工具。" : "The Agent understands the goal, selects authorized Skills, checks evidence, and makes uncertainty explicit. No tool setup required."}</p></div>
            <div className="mt-7 grid gap-3 sm:grid-cols-2">{starterPrompts.map((item) => <button key={item.title} type="button" onClick={() => choosePrompt(item.body)} className="group rounded-2xl border border-border-pg bg-bg-panel p-4 text-left shadow-card transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-border-pg-strong hover:shadow-card-hover focus-visible:border-border-pg-strong motion-reduce:hover:translate-y-0"><span className="text-sm font-medium">{item.title}</span><span className="mt-1.5 block text-xs leading-5 text-text-pg-dim">{item.body}</span><span className="mt-3 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-text-pg-muted"><Target className="h-3 w-3" />{zh ? "作为目标使用" : "Use as goal"}</span></button>)}</div>
          </div> : null}
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((message) => {
              const citationIndices = new Set(message.sources.map((source) => source.citation_index));
              return <div key={message.id} id={`message-${message.id}`} tabIndex={-1} className={message.role === "user" ? "ml-auto max-w-[min(85%,42rem)] break-words rounded-2xl border border-border-pg bg-bg-panel-muted p-4 text-sm outline-none" : "min-w-0 max-w-full overflow-x-auto rounded-2xl border border-border-pg bg-bg-panel p-4 shadow-card outline-none"} aria-busy={message.status === "streaming" ? true : undefined}>
              {message.role === "assistant" ? <><div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-text-pg-dim"><span>{bylineModelLabel(message.model, modelCopy, defaultModelName, modelLabels)}</span>{message.context?.runtime?.intent ? <span className="rounded-lg border border-border-pg px-1.5 py-0.5 normal-case">{message.context.runtime.intent.replaceAll("_", " ")}</span> : null}{message.context?.evidence ? <span className={`inline-flex items-center gap-1 rounded-lg border px-1.5 py-0.5 normal-case ${message.context.evidence.sufficient ? "border-border-pg text-text-pg-muted" : "border-status-warning text-status-warning"}`}><SearchCheck className="h-3 w-3" />{zh ? "证据" : "Evidence"} · {message.context.evidence.sufficient ? (zh ? "通过" : "met") : (zh ? "缺口" : "gaps")}</span> : null}</div>
                {message.status === "streaming" && !message.content ? <p className="flex items-center gap-1.5 text-xs text-text-pg-dim" role="status"><span className="inline-flex gap-0.5" aria-hidden><span className="h-1 w-1 animate-pulse rounded-full bg-current motion-reduce:animate-none" /><span className="h-1 w-1 animate-pulse rounded-full bg-current [animation-delay:150ms] motion-reduce:animate-none" /><span className="h-1 w-1 animate-pulse rounded-full bg-current [animation-delay:300ms] motion-reduce:animate-none" /></span>{zh ? "正在生成" : "Writing"}</p> : <ReportMarkdown content={linkCitations(message.content, message.id, citationIndices)} locale={locale} />}
                {message.context?.tool_results?.map((result, index) => <StrategyToolResult key={`${message.id}-${result.tool}-${index}`} result={result} locale={locale} />)}</> : <><p className="whitespace-pre-wrap leading-6">{message.content}</p>{message.context ? <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border-pg pt-2 text-[10px] text-text-pg-dim">{message.context.data_sources?.map((item) => <span key={item} className="rounded-lg border border-border-pg px-1.5 py-0.5">{item}</span>)}{message.context.skills?.map((item) => typeof item === "string" ? <span key={item} className="rounded-lg border border-border-pg px-1.5 py-0.5">{item.replaceAll("_", " ")}</span> : null)}{message.context.attachments?.length ? <AttachmentCards files={message.context.attachments} locale={locale} /> : null}</div> : null}</>}
              {message.status === "failed" ? <div className="mt-3 rounded-lg border border-status-negative p-3 text-sm text-status-negative"><p>{message.error_message}</p><button type="button" onClick={() => { setInput([...messages].reverse().find((item) => item.role === "user" && item.created_at <= message.created_at)?.content || ""); window.setTimeout(() => composerRef.current?.focus(), 0); }} className="mt-2 inline-flex items-center gap-2 rounded-lg border border-border-pg px-2 py-1"><RefreshCw className="h-3.5 w-3.5" />{zh ? "重新提问" : "Ask again"}</button></div> : null}
              {message.role === "assistant" && (message.sources.length || message.context?.evidence) ? (
                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                  <button type="button" onClick={(event) => openInspector({ messageId: message.id }, event.currentTarget)} data-testid="open-evidence" className={`inline-flex min-h-8 items-center gap-1.5 rounded-lg border px-2.5 ${message.context?.evidence && !message.context.evidence.sufficient ? "border-status-warning text-status-warning" : "border-border-pg text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"}`}>
                    <Database className="h-3.5 w-3.5" aria-hidden />
                    {zh ? `来源 ${message.sources.length}` : `Sources ${message.sources.length}`}
                    {message.context?.evidence ? <span>· {message.context.evidence.sufficient ? (zh ? "证据通过" : "evidence met") : (zh ? `证据缺口：${message.context.evidence.missing.join(", ")}` : `gaps: ${message.context.evidence.missing.join(", ")}`)}</span> : null}
                  </button>
                </div>
              ) : null}
              {message.role === "assistant" && message.status === "completed" && message.credits_used != null ? <div className="mt-3 text-right text-[10px] text-text-pg-dim">{zh ? "实际消耗" : "Actual cost"}: {message.credits_used} Credits</div> : null}
              {message.role === "assistant" && message.credits_refunded ? <div className="mt-3 text-right text-[10px] text-text-pg-dim">{zh ? "Credits 已退款" : "Credits refunded"}</div> : null}
              {message.id === latestAssistantId && message.context?.runtime?.next_actions?.length ? <div className="mt-4 flex flex-wrap gap-2">{message.context.runtime.next_actions.slice(0, 3).map((action) => <button key={action} type="button" onClick={() => choosePrompt(nextActionPrompt(action, zh))} className="inline-flex items-center gap-1.5 rounded-lg border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"><CheckCircle2 className="h-3 w-3" />{nextActionLabel(action, zh)}</button>)}</div> : null}
              {message.id === latestAssistantId && message.status === "completed" ? (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-border-pg pt-3">
                  <Link href={withLocale(locale, "/research")} className="inline-flex items-center gap-1.5 rounded-lg border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"><FlaskConical className="h-3 w-3" />{zh ? "生成交易研究" : "Generate trading research"}</Link>
                  <Link href={withLocale(locale, "/strategies")} className="inline-flex items-center gap-1.5 rounded-lg border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"><Target className="h-3 w-3" />{zh ? "生成策略草案" : "Draft a strategy"}</Link>
                  <Link href={withLocale(locale, "/trading/risk")} className="inline-flex items-center gap-1.5 rounded-lg border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"><ShieldCheck className="h-3 w-3" />{zh ? "进入交易安全页" : "Trading safety"}</Link>
                </div>
              ) : null}
            </div>;
            })}
            {working && runtimePlan ? <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-pg bg-bg-app px-3 py-2 text-xs text-text-pg-muted"><Target className="h-3.5 w-3.5" /><span>{zh ? "已理解" : "Understood"}: {runtimePlan.intent.replaceAll("_", " ")}</span>{runtimePlan.assets.length ? <span className="text-text-pg-dim">· {runtimePlan.assets.join(", ")}</span> : null}{evidenceStatus ? <span className={evidenceStatus.sufficient ? "ml-auto text-text-pg-muted" : "ml-auto text-status-warning"}>{evidenceStatus.sufficient ? (zh ? "证据已就绪" : "Evidence ready") : (zh ? "证据存在缺口" : "Evidence gaps found")}</span> : <span className="ml-auto text-text-pg-dim">{zh ? "正在构建证据包" : "Building evidence pack"}</span>}</div> : null}
            <AgentStageIndicator stage={stage} locale={locale} />
            {connection === "recovering" ? <p role="status" data-testid="chat-reconnecting" className="flex items-center gap-2 text-xs text-status-warning"><WifiOff className="h-3.5 w-3.5" aria-hidden />{zh ? "连接中断，正在从服务端事件日志恢复——尚未判定失败。" : "Connection interrupted. Restoring from the server's event log — nothing has been marked failed."}</p> : null}
            {observing && connection !== "recovering" ? <p role="status" data-testid="chat-observing" className="flex items-center gap-2 text-xs text-text-pg-muted"><Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />{zh ? "此对话有一轮仍在服务端进行，正在按事件日志跟进。" : "A turn in this conversation is still running on the server; following its event log."}</p> : null}
            {working && dreamProgress ? <div className="flex items-center gap-2 rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 text-xs text-text-pg-muted" data-testid="dream-rsi-progress"><span className="h-2 w-2 animate-pulse rounded-full bg-current motion-reduce:animate-none" /><span>Dream-RSI · {dreamProgress.status.replaceAll("_", " ")}</span>{dreamProgress.evaluations ? <span className="ml-auto">{dreamProgress.evaluations} {zh ? "次评估" : "evaluations"}</span> : null}</div> : null}
            <ToolTimeline steps={toolSteps} locale={locale} />
            {approval ? <ToolApprovalCard approval={approval} locale={locale} busy={approving} onDecide={async (decision) => { setApproving(true); try { await approveAgentTool(approval.toolCallId, decision); setApproval(null); } catch { setFailure({ kind: "generic", message: zh ? "批准已过期或无法提交，请刷新会话。" : "Approval expired or could not be submitted. Refresh the conversation.", billing: "unknown" } as ChatFailure); } finally { setApproving(false); } }} /> : null}

            {working ? toolResults.map((result, index) => <StrategyToolResult key={`${result.tool}-${index}`} result={result} locale={locale} />) : null}
            {stopped ? <p role="status" data-testid="chat-stopped" className="text-xs text-text-pg-muted">{zh ? "已停止生成。已完成的工具调用不会被撤销；本轮按实际用量结算。" : "Generation stopped. Tool calls that already ran are not undone; this turn is settled on actual usage."}</p> : null}
          </div>
        </div>
        <div className="shrink-0 border-t border-border-pg bg-bg-panel p-3 md:p-4" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
          <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2 lg:hidden">
            <button ref={historyTriggerRef} type="button" onClick={() => setMobileHistoryOpen(true)} aria-label={zh ? "历史对话" : "Conversation history"} aria-expanded={mobileHistoryOpen} aria-controls={mobileHistoryOpen ? "chat-history-drawer" : undefined} aria-haspopup="dialog" data-testid="chat-history-trigger" className="flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm hover:bg-[var(--pg-surface-hover)]"><PanelLeftOpen className="h-4 w-4" />{zh ? "历史" : "History"}</button>
            <button type="button" onClick={() => void createNew()} aria-label={zh ? "新会话" : "New conversation"} data-testid="chat-new-trigger" className="grid h-10 w-10 place-items-center rounded-lg hover:bg-[var(--pg-surface-hover)]"><MessageSquarePlus className="h-4 w-4" /></button>
          </div>
          {recovered ? (
            <div className="mx-auto mb-2 max-w-3xl rounded-lg border border-status-positive px-3 py-2 text-xs text-status-positive" data-testid="chat-recovered" role="status">
              {zh ? "连接曾中断，已从服务端事件日志恢复这一轮。" : "The connection dropped; this turn was restored from the server's event log."}
            </div>
          ) : null}
          <ChatWorkspaceComposer locale={locale} input={input} onInput={setInput} busy={working} onSend={() => void send()} onStop={() => void stop()} attachments={attachments} onAttachments={setAttachments} permission={permission} onUploading={setUploading}
            onPermission={async (mode) => { if (conversationId) await setAgentPermission(conversationId, mode); setPermission(mode); }}
            researchMode={researchMode} onResearch={setResearchMode} onTextarea={node => { composerRef.current = node; }}
            modelControl={<select id="agent-model" aria-label={zh ? "模型" : "Model"} value={selectedModel} onChange={event => setSelectedModel(event.target.value)} disabled={working} className="min-h-10 max-w-[220px] rounded-xl border border-border-pg bg-bg-panel-muted px-3 text-xs font-medium text-text-pg disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text-pg">{usableModels.map(model => <option key={model.id} value={model.id} data-provider={model.provider}>{agentModelLabel(model, modelCopy, defaultModelName, zh)}</option>)}</select>}
            modelNote={lockedModelNote(models, zh)}
            settings={<ContextControls locale={locale} plugins={plugins} pluginCounts={pluginCounts} skills={skills} customPrompt={customPrompt} onPrompt={setCustomPrompt} />} />
          {input.trim() && creditQuote && !creditQuote.unavailable ? <p className="mx-auto mt-2 max-w-3xl text-right text-xs text-text-pg-muted" data-testid="chat-estimate">{zh ? "预计" : "Estimated"} {estimatedCredits} Credits{creditQuote.reservation_amount ? (zh ? ` · 发送时预留 ${creditQuote.reservation_amount}，按实际结算` : ` · ${creditQuote.reservation_amount} reserved on send, settled on actual use`) : ""}</p> : null}
          {failure ? (
            <div className="mx-auto mt-2 max-w-3xl rounded-lg border border-status-negative px-3 py-2 text-xs text-status-negative" role="alert" data-testid="chat-error">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1">{failure.message}</span>
                {failure.reference ? <span className="font-mono text-[10px] text-text-pg-dim" data-testid="chat-error-reference">{modelCopy.errors.reference}: {failure.reference}</span> : null}
                {unsentAttempt ? <button type="button" data-testid="chat-retry-safely" onClick={() => void send(undefined, unsentAttempt)} className="rounded-lg border border-border-pg px-2 py-1 text-[11px] text-text-pg hover:border-border-pg-strong">{zh ? "安全重试（不会重复提交）" : "Retry safely (no duplicate)"}</button> : null}
                <button type="button" onClick={() => { setFailure(null); setUnsentAttempt(null); }} className="rounded-lg border border-border-pg px-2 py-1 text-[10px] text-text-pg-muted">{zh ? "关闭" : "Dismiss"}</button>
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
      {/* Phone history drawer, portalled to <body>: inside the chat card the
          glass skin's backdrop-filter made "fixed" relative to the card, so
          the drawer was clipped under the app header with its close button
          hidden, and the transcript showed through it. */}
      {mobileHistoryOpen ? createPortal(
        <>
          <button type="button" aria-label={zh ? "关闭历史对话" : "Close conversation history"} onClick={closeMobileHistory} className="fixed inset-0 z-[60] bg-black/40 lg:hidden" />
          <aside ref={historyPanelRef} id="chat-history-drawer" role="dialog" aria-modal="true" aria-label={zh ? "历史对话" : "Conversation history"} className="fixed inset-y-3 left-3 z-[61] flex w-80 max-w-[85vw] flex-col overflow-hidden rounded-2xl border border-border-pg shadow-2xl lg:hidden" style={{ background: "var(--pg-bg-page)", paddingBottom: "env(safe-area-inset-bottom)" }}>
        <div className="flex items-center justify-between border-b border-border-pg p-3">
          <div className="min-w-0"><div className="text-xs uppercase text-text-pg-dim">PureGamma Agent</div><div className="mt-1 truncate text-[11px] text-text-pg-dim" data-testid="chat-usage-summary">{quota ? `${quota.remaining}/${quota.limit} ${zh ? "今日剩余" : "left today"} · ${quota.credit_balance} Credits` : "-"}</div></div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setHistoryCollapsed(true)} className="hidden h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong lg:grid" aria-label={zh ? "收起历史对话" : "Collapse conversation history"} aria-expanded><PanelLeftClose className="h-4 w-4" /></button>
            <button type="button" onClick={closeMobileHistory} className="grid h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong lg:hidden" aria-label={zh ? "关闭历史对话" : "Close conversation history"}><X className="h-4 w-4" /></button>
            <button type="button" onClick={() => void createNew()} className="grid h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong" aria-label={zh ? "新会话" : "New conversation"}><MessageSquarePlus className="h-4 w-4" /></button>
          </div>
        </div>
        <div className="space-y-2 border-b border-border-pg p-2">
          <label className="flex items-center gap-2 rounded-lg bg-bg-panel px-2 focus-within:ring-2 focus-within:ring-[var(--pg-focus-ring)]">
            <Search className="h-3.5 w-3.5 shrink-0 text-text-pg-dim" aria-hidden />
            <span className="sr-only">{zh ? "搜索历史对话" : "Search conversations"}</span>
            <input type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder={zh ? "搜索标题" : "Search titles"} className="min-h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" data-testid="chat-history-search" />
          </label>
          <div className="flex gap-1 text-xs" role="group" aria-label={zh ? "历史筛选" : "History filter"}>
            <button type="button" aria-pressed={!showArchived} onClick={() => setShowArchived(false)} className={`min-h-8 flex-1 rounded-md px-2 ${!showArchived ? "bg-bg-panel text-text-pg" : "text-text-pg-muted hover:text-text-pg"}`}>{zh ? "进行中" : "Active"}</button>
            <button type="button" aria-pressed={showArchived} onClick={() => setShowArchived(true)} className={`min-h-8 flex-1 rounded-md px-2 ${showArchived ? "bg-bg-panel text-text-pg" : "text-text-pg-muted hover:text-text-pg"}`}>{zh ? `已归档 ${archivedCount}` : `Archived ${archivedCount}`}</button>
          </div>
        </div>
        {historyError ? <p role="alert" className="mx-2 mt-2 rounded-md px-2 py-1.5 text-xs text-status-negative">{historyError}</p> : null}
        <div className="flex-1 overflow-y-auto p-2 lg:space-y-1">
          {visibleConversations.map((conversation) => (
            <div key={conversation.id} className="group flex items-center">
              <button type="button" aria-current={conversation.id === conversationId ? "page" : undefined} onClick={() => { router.push(withLocale(locale, `/chat/${conversation.id}`)); void openConversation(conversation.id); if (mobileHistoryOpen) closeMobileHistory(); }} className={`min-w-0 flex-1 rounded-xl border px-3 py-2 text-left text-sm ${conversation.id === conversationId ? "border-border-pg bg-bg-panel shadow-card" : "border-transparent text-text-pg-muted hover:border-border-pg hover:bg-bg-panel"}`}>
                <div className="truncate font-medium">{conversation.title}</div>
                <div className="mt-1 text-xs text-text-pg-dim">{new Date(conversation.updated_at).toLocaleDateString(locale)}</div>
              </button>
              <div className="ml-0.5 flex shrink-0 lg:invisible lg:group-hover:visible lg:group-focus-within:visible">
                <button type="button" onClick={(event) => { event.stopPropagation(); void setArchived(conversation.id, !conversation.archived_at); }} aria-label={conversation.archived_at ? (zh ? `取消归档：${conversation.title}` : `Unarchive: ${conversation.title}`) : (zh ? `归档：${conversation.title}` : `Archive: ${conversation.title}`)} className="grid h-9 w-8 place-items-center rounded-lg border border-transparent text-text-pg-dim hover:border-border-pg hover:text-text-pg">{conversation.archived_at ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}</button>
                <button type="button" onClick={(event) => { event.stopPropagation(); void deleteConversation(conversation.id); }} aria-label={zh ? `删除会话：${conversation.title}` : `Delete conversation: ${conversation.title}`} className="grid h-9 w-8 place-items-center rounded-lg border border-transparent text-text-pg-dim hover:border-status-negative hover:text-status-negative"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
          ))}
          {visibleConversations.length === 0 ? <div className="px-3 py-4 text-center text-xs text-text-pg-dim">{query ? (zh ? "没有匹配的对话" : "No matching conversations") : showArchived ? (zh ? "没有已归档的对话" : "No archived conversations") : (zh ? "暂无历史对话" : "No conversation history")}</div> : null}
        </div>
        {conversations.length ? (
          <div className="border-t border-border-pg p-2">
            <button type="button" onClick={() => void deleteAll()} className="flex w-full items-center justify-center gap-2 rounded-lg border border-border-pg px-3 py-2 text-xs text-text-pg-dim transition-colors hover:border-status-negative hover:text-status-negative" aria-label={zh ? "删除全部历史对话" : "Delete all conversation history"}>
              <Trash2 className="h-3.5 w-3.5" />
              <span>{zh ? "删除全部历史对话" : "Delete all history"}</span>
            </button>
          </div>
        ) : null}
          </aside>
        </>,
        document.body,
      ) : null}
      {inspector && inspectorMessage ? <EvidenceInspector locale={locale} messageId={inspectorMessage.id} sources={inspectorMessage.sources} evidence={inspectorMessage.context?.evidence} focus={inspector.focus} onClose={closeInspector} /> : null}
    </OceanShell>
  );
}

