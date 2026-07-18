"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, CircleStop, Database, FilePlus2, Loader2, MessageSquarePlus, Paperclip, RefreshCw, Send, Settings2, Sparkles, Wrench, X } from "lucide-react";
import { ReportMarkdown } from "@/components/puregamma";
import { type Locale, withLocale } from "@/i18n/routing";
import { AgentAttachment, AgentCapabilities, AgentConversation, AgentMessage, AgentModelOption, AgentSource, SkillContextRef, SkillSummary, cancelAgentRun, createAgentConversation, getAgentCapabilities, getAgentConversation, getAgentConversations, getAgentQuota, getCreditQuote, getMe, streamAgentMessage } from "@/lib/api";
import { publishCreditBalance } from "@/lib/user-state";

const DATA_SOURCES = ["market", "rss", "fintwit", "x-twitter", "bloomberg", "portfolio", "options"];

export function AgentChat({ locale, initialConversationId }: { locale: Locale; initialConversationId?: string }) {
  const router = useRouter();
  const zh = locale === "zh";
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [conversationId, setConversationId] = useState(initialConversationId || "");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toolStatus, setToolStatus] = useState<string[]>([]);
  const [toolResults, setToolResults] = useState<Array<{ tool: string; data: Record<string, unknown> }>>([]);
  const [quota, setQuota] = useState<{ remaining: number | null; limit: number | null; credit_balance: number } | null>(null);
  const [capabilities, setCapabilities] = useState<AgentCapabilities | null>(null);
  const [models, setModels] = useState<AgentModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("default");
  const [dataSources, setDataSources] = useState<string[]>(["market", "rss"]);
  const [skillCatalog, setSkillCatalog] = useState<SkillSummary[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [customPrompt, setCustomPrompt] = useState("");
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const controllerRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const activeRunRef = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  const loadConversations = async () => {
    const result = await getAgentConversations();
    setConversations(result.conversations);
    return result.conversations;
  };

  const openConversation = async (id: string) => {
    const result = await getAgentConversation(id);
    setConversationId(id);
    setMessages(result.messages);
    setError("");
  };

  useEffect(() => {
    let active = true;
    Promise.all([getMe(), loadConversations(), getAgentCapabilities()])
      .then(async ([, rows, access]) => {
        if (!active) return;
        setQuota(access.quota);
        setCapabilities(access.capabilities);
        setModels(access.models);
        setSkillCatalog(access.skills);
        setSkills((current) => current.length ? current : access.skills.filter((skill) => ["market_research", "news_research"].includes(skill.slug)).map((skill) => skill.skill_id));
        const target = initialConversationId || rows[0]?.id;
        if (target) await openConversation(target);
      })
      .catch((reason: Error & { status?: number }) => {
        if (reason.status === 401) router.replace(`${withLocale(locale, "/login")}?returnTo=${encodeURIComponent(withLocale(locale, "/chat"))}`);
        else if (active) setError(reason.message);
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; controllerRef.current?.abort(); };
  }, [initialConversationId, locale, router]);

  useEffect(() => {
    if (followRef.current) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, toolStatus]);

  const createNew = async () => {
    const result = await createAgentConversation();
    setConversations((current) => [result.conversation, ...current]);
    setConversationId(result.conversation.id);
    setMessages([]);
    router.push(withLocale(locale, `/chat/${result.conversation.id}`));
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
    const content = input.trim();
    if (!content || busy) return;
    setBusy(true);
    setError("");
    setToolStatus([]);
    setToolResults([]);
    followRef.current = true;
    try {
      const id = await ensureConversation();
      setInput("");
      const now = new Date().toISOString();
      const skillRefs: SkillContextRef[] = skillCatalog.filter((skill) => skills.includes(skill.skill_id)).map((skill) => ({ skill_id: skill.skill_id, slug: skill.slug, version: skill.current_version, installation_id: skill.installation_id }));
      const context = { data_sources: dataSources, skills: skillRefs, skill_refs: skillRefs, custom_prompt: customPrompt, attachments, model: selectedModel };
      setMessages((current) => [...current, { id: `local-${Date.now()}`, conversation_id: id, role: "user", content, status: "completed", input_tokens: 0, output_tokens: 0, created_at: now, context, sources: [] }]);
      const controller = new AbortController();
      controllerRef.current = controller;
      let assistantId = "";
      await streamAgentMessage(id, content, locale, controller.signal, ({ event: eventName, data }) => {
        if (eventName === "run.started") {
          activeRunRef.current = String(data.runId || "");
          assistantId = String(data.messageId || `assistant-${Date.now()}`);
          setMessages((current) => [...current, { id: assistantId, conversation_id: id, role: "assistant", content: "", status: "streaming", model: String(data.model || selectedModel), input_tokens: 0, output_tokens: 0, created_at: new Date().toISOString(), sources: [] }]);
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        } else if (eventName === "message.delta") {
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, content: `${message.content}${String(data.delta || "")}` } : message));
        } else if (eventName === "tool.started") {
          setToolStatus((current) => [...current, `${String(data.tool)} · ${zh ? "检索中" : "retrieving"}`]);
        } else if (eventName === "tool.completed") {
          setToolStatus((current) => current.map((item) => item.startsWith(String(data.tool)) ? `${String(data.tool)} · ${data.error ? (zh ? "失败" : "failed") : (zh ? "完成" : "complete")}` : item));
          if (data.data && typeof data.data === "object") setToolResults((current) => [...current, { tool: String(data.tool), data: data.data as Record<string, unknown> }]);
        } else if (eventName === "citation") {
          const source: AgentSource = { provider: String(data.provider), title: String(data.title), url: data.url ? String(data.url) : null, published_at: data.publishedAt ? String(data.publishedAt) : null, source_timestamp: data.sourceTimestamp ? String(data.sourceTimestamp) : null, fetched_at: String(data.fetchedAt), citation_index: Number(data.index) };
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, sources: [...message.sources, source] } : message));
        } else if (eventName === "message.completed") {
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "completed", model: String(data.model || message.model || ""), input_tokens: Number(data.inputTokens || 0), output_tokens: Number(data.outputTokens || 0), credits_used: Number(data.creditsUsed || 0) } : message));
          setQuota((current) => current ? { ...current, credit_balance: Number(data.creditBalance ?? current.credit_balance) } : current);
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        } else if (eventName === "run.failed") {
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "failed", error_code: String(data.code), error_message: String(data.message) } : message));
          setError(String(data.message || (zh ? "Agent 运行失败" : "Agent run failed")));
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        } else if (eventName === "run.canceled") {
          if (typeof data.creditBalance === "number") publishCreditBalance(data.creditBalance);
        }
      }, context);
      setAttachments([]);
      const refreshed = await getAgentConversation(id);
      setMessages(refreshed.messages);
      await loadConversations();
      const refreshedQuota = await getAgentQuota();
      setQuota(refreshedQuota);
      publishCreditBalance(refreshedQuota.credit_balance);
    } catch (reason) {
      if ((reason as Error).name !== "AbortError") setError((reason as Error).message);
    } finally {
      setBusy(false);
      activeRunRef.current = "";
      controllerRef.current = null;
    }
  };

  const stop = async () => {
    if (activeRunRef.current) await cancelAgentRun(activeRunRef.current).catch(() => undefined);
    controllerRef.current?.abort();
    setBusy(false);
  };

  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    const accepted: AgentAttachment[] = [];
    let totalBytes = attachments.reduce((sum, item) => sum + new TextEncoder().encode(item.content).length, 0);
    for (const file of Array.from(files).slice(0, 5 - attachments.length)) {
      if (file.size > 20_000 || totalBytes + file.size > 50_000 || !(/text|json|csv|markdown/.test(file.type) || /\.(txt|md|csv|json)$/i.test(file.name))) {
        setError(zh ? `${file.name} 不支持；单文件上限 20KB、总上限 50KB，仅接受文本、Markdown、CSV 或 JSON。` : `${file.name} is unsupported; files are limited to 20KB each and 50KB total.`);
        continue;
      }
      const content = await file.text();
      totalBytes += new TextEncoder().encode(content).length;
      accepted.push({ name: file.name, content, mime: file.type || "text/plain" });
    }
    setAttachments((current) => [...current, ...accepted].slice(0, 5));
    if (fileRef.current) fileRef.current.value = "";
  };

  const toggle = (value: string, current: string[], update: (next: string[]) => void) => update(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  const selectedModelOption = models.find((model) => model.id === selectedModel);
  const [creditQuote, setCreditQuote] = useState<{ estimated_min: number; estimated_max: number; reservation_amount?: number; unavailable?: boolean } | null>(null);
  useEffect(() => {
    const deepResearch = skillCatalog.some((skill) => skill.slug === "deep_research" && skills.includes(skill.skill_id));
    const taskType = deepResearch
      ? (selectedModel === "default" ? "agent_deep_research" : "luna_deep_research")
      : (selectedModel === "default" ? "agent_chat_basic" : "agent_luna_research");
    const timer = window.setTimeout(() => {
      getCreditQuote({
        task_type: taskType,
        requested_model: selectedModel,
        input_tokens: Math.max(0, Math.ceil(new TextEncoder().encode(input).length / 4)),
        selected_data_sources: dataSources,
        attachment_bytes: attachments.reduce((sum, item) => sum + new TextEncoder().encode(item.content || "").length, 0),
      }, locale).then(setCreditQuote).catch(() => setCreditQuote({ estimated_min: 0, estimated_max: 0, unavailable: true }));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [selectedModel, dataSources, skills, skillCatalog, attachments, input, locale]);
  const estimatedCredits = creditQuote
    ? creditQuote.estimated_min === creditQuote.estimated_max
      ? String(creditQuote.estimated_min)
      : `${creditQuote.estimated_min}-${creditQuote.estimated_max}`
    : "-";

  return (
    <div className="grid h-[calc(100dvh-7rem)] min-h-[620px] overflow-hidden border border-border-pg bg-bg-panel lg:grid-cols-[244px_minmax(0,1fr)] xl:grid-cols-[244px_minmax(0,1fr)_286px]">
      <aside className="hidden border-b border-border-pg bg-bg-app lg:block lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between border-b border-border-pg p-3">
          <div><div className="text-xs uppercase text-text-pg-dim">PureGamma Agent</div><div className="mt-1 text-xs text-text-pg-muted">{quota ? `${quota.remaining}/${quota.limit} ${zh ? "今日剩余" : "remaining"} · ${quota.credit_balance} Credits` : "-"}</div></div>
          <button type="button" onClick={createNew} className="grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong" title={zh ? "新会话" : "New conversation"}><MessageSquarePlus className="h-4 w-4" /></button>
        </div>
        <div className="flex gap-2 overflow-x-auto p-2 lg:block lg:max-h-[calc(100vh-13rem)] lg:space-y-1 lg:overflow-y-auto">
          {conversations.map((conversation) => <button key={conversation.id} type="button" onClick={() => { router.push(withLocale(locale, `/chat/${conversation.id}`)); openConversation(conversation.id); }} className={`min-w-52 border px-3 py-2 text-left text-sm lg:block lg:w-full lg:min-w-0 ${conversation.id === conversationId ? "border-border-pg-strong bg-bg-panel-muted" : "border-transparent text-text-pg-muted hover:border-border-pg"}`}><div className="truncate font-medium">{conversation.title}</div><div className="mt-1 text-xs text-text-pg-dim">{new Date(conversation.updated_at).toLocaleDateString(locale)}</div></button>)}
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden">
        <div ref={scrollRef} onScroll={(event) => { const target = event.currentTarget; followRef.current = target.scrollHeight - target.scrollTop - target.clientHeight < 120; }} className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          {loading ? <div className="grid min-h-64 place-items-center"><Loader2 className="h-5 w-5 animate-spin" /></div> : null}
          {!loading && messages.length === 0 ? <div className="mx-auto grid min-h-[50vh] max-w-xl place-items-center text-center"><div><Bot className="mx-auto h-7 w-7 text-text-pg-muted" /><h1 className="mt-4 text-xl font-semibold">{zh ? "寻找未来一周的Beta、Alpha 与 Long Gamma AI" : "Find next week's Beta, Alpha & Long Gamma AI"}</h1><p className="mt-2 text-sm leading-6 text-text-pg-muted">{zh ? "开始对话" : "Start Chat"}</p></div></div> : null}
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((message) => <div key={message.id} className={message.role === "user" ? "ml-auto max-w-[85%] border border-border-pg-strong bg-bg-panel-muted p-3 text-sm" : "max-w-full border-l border-border-pg pl-4"}>
              {message.role === "assistant" ? <><div className="mb-2 text-[10px] uppercase tracking-wide text-text-pg-dim">{message.model === "gpt-5.6-luna" ? "GPT-5.6 Luna · OpenAI" : (message.model || (zh ? "默认模型" : "Default model"))}</div><ReportMarkdown content={message.content || (message.status === "streaming" ? (zh ? "正在分析..." : "Analyzing...") : "")} locale={locale} /></> : <><p className="whitespace-pre-wrap leading-6">{message.content}</p>{message.context ? <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border-pg pt-2 text-[10px] text-text-pg-dim">{message.context.data_sources?.map((item) => <span key={item} className="border border-border-pg px-1.5 py-0.5">{item}</span>)}{message.context.skills?.map((item) => { const slug = typeof item === "string" ? item : item.slug; const version = typeof item === "string" ? null : item.version; return <span key={typeof item === "string" ? item : `${item.skill_id}-${item.version}`} className="border border-border-pg px-1.5 py-0.5">{slug.replaceAll("_", " ")}{version ? ` · v${version}` : ""}</span>; })}{message.context.attachments?.map((file) => <span key={file.name} className="border border-border-pg px-1.5 py-0.5">{file.name}</span>)}</div> : null}</>}
              {message.status === "failed" ? <div className="mt-3 border border-status-negative p-3 text-sm text-status-negative"><p>{message.error_message}</p><button type="button" onClick={() => { setInput(messages.find((item) => item.role === "user" && item.created_at <= message.created_at)?.content || ""); }} className="mt-2 inline-flex items-center gap-2 border border-border-pg px-2 py-1"><RefreshCw className="h-3.5 w-3.5" />{zh ? "重试" : "Retry"}</button></div> : null}
              {message.role === "assistant" && message.status === "completed" && message.credits_used != null ? <div className="mt-3 text-right text-[10px] text-text-pg-dim">{zh ? "实际消耗" : "Actual cost"}: {message.credits_used} Credits</div> : null}
              {message.role === "assistant" && message.credits_refunded ? <div className="mt-3 text-right text-[10px] text-text-pg-dim">{zh ? "Credits 已退款" : "Credits refunded"}</div> : null}
              {message.status === "streaming" && message.sources.length ? <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[10px] text-text-pg-dim"><span className="font-semibold">{zh ? "来源" : "Sources"}:</span>{message.sources.map((source) => <span key={`${message.id}-${source.citation_index}`} className="truncate border border-border-pg px-1.5 py-0.5 max-w-[160px]">[{source.citation_index}] {source.title}</span>)}</div> : null}
            </div>)}
            {toolStatus.length ? <div className="flex flex-wrap gap-2">{toolStatus.map((item) => <span key={item} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs text-text-pg-muted"><Wrench className="h-3 w-3" />{item}</span>)}</div> : null}
            {toolResults.map((result, index) => <StrategyToolResult key={`${result.tool}-${index}`} result={result} locale={locale} />)}
          </div>
        </div>
        <div className="shrink-0 border-t border-border-pg bg-bg-app p-3 md:p-4">
          <div className="mx-auto mb-2 flex max-w-3xl items-center justify-between gap-3">
            <label htmlFor="agent-model" className="text-[11px] text-text-pg-muted"><span className="block">{zh ? "本轮模型" : "Model for this turn"}</span>{selectedModelOption?.id !== "default" ? <span className="mt-0.5 block text-[10px] text-text-pg-dim">{zh ? "高质量、较轻度使用的深度市场研究模型" : selectedModelOption?.description}</span> : null}</label>
            <select id="agent-model" value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} disabled={busy} className="border border-border-pg bg-bg-panel px-2 py-1 text-xs outline-none focus:border-border-pg-strong disabled:opacity-50">
              {models.map((model) => <option key={model.id} value={model.id} disabled={!model.available}>{model.display_name}{model.id === "default" ? "" : model.available ? ` · ${model.credit_cost} Credits` : model.reason === "plan_required" ? (zh ? " · 需要 Max/Enterprise" : " · Max/Enterprise required") : (zh ? " · 当前不可用" : " · unavailable")}</option>)}
            </select>
          </div>
          <details className="mx-auto mb-3 max-w-3xl border border-border-pg bg-bg-panel xl:hidden"><summary className="flex cursor-pointer items-center gap-2 p-3 text-xs font-medium"><Settings2 className="h-4 w-4" />{zh ? "本轮上下文" : "Turn context"}<span className="ml-auto text-text-pg-dim">{dataSources.length + skills.length + attachments.length}</span></summary><div className="border-t border-border-pg p-3"><ContextControls locale={locale} dataSources={dataSources} skills={skills} skillCatalog={skillCatalog} customPrompt={customPrompt} attachments={attachments} allowedSources={capabilities?.allowed_data_sources || []} onToggleSource={(value) => toggle(value, dataSources, setDataSources)} onToggleSkill={(value) => toggle(value, skills, setSkills)} onPrompt={setCustomPrompt} onRemoveFile={(name) => setAttachments((current) => current.filter((file) => file.name !== name))} /></div></details>
          <form onSubmit={send} className="mx-auto flex max-w-3xl items-end gap-2">
            <input ref={fileRef} type="file" multiple accept=".txt,.md,.csv,.json,text/plain,text/markdown,text/csv,application/json" className="hidden" onChange={(event) => void addFiles(event.target.files)} />
            <button type="button" onClick={() => fileRef.current?.click()} className="grid h-14 w-11 shrink-0 place-items-center border border-border-pg hover:border-border-pg-strong" title={zh ? "添加文件" : "Add files"}><Paperclip className="h-4 w-4" /></button>
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} rows={2} placeholder={zh ? "输入研究问题，Shift + Enter 换行" : "Ask a research question, Shift + Enter for a new line"} className="min-h-14 flex-1 resize-none border border-border-pg bg-bg-panel px-3 py-2 text-sm outline-none focus:border-border-pg-strong" />
            {busy ? <button type="button" onClick={stop} className="grid h-14 w-12 place-items-center border border-border-pg text-status-negative" title={zh ? "停止生成" : "Stop generation"}><CircleStop className="h-5 w-5" /></button> : <button type="submit" disabled={!input.trim()} className="grid h-14 w-12 place-items-center border border-border-pg-strong bg-pg-white text-pg-black disabled:opacity-40" title={zh ? "发送" : "Send"}><Send className="h-5 w-5" /></button>}
          </form>
          <p className="mx-auto mt-2 max-w-3xl text-right text-[11px] text-text-pg-dim">{creditQuote?.unavailable ? (zh ? "计费报价暂不可用" : "Credit quote unavailable") : `${zh ? "预计消耗" : "Estimated cost"}: ${estimatedCredits} Credits`}</p>
          {error ? <p className="mx-auto mt-2 max-w-3xl text-xs text-status-negative">{error}</p> : null}
        </div>
      </section>
      <aside className="hidden min-h-0 overflow-y-auto border-l border-border-pg bg-bg-app xl:block">
        <div className="sticky top-0 border-b border-border-pg bg-bg-app p-4"><div className="flex items-center gap-2 text-xs uppercase text-text-pg-dim"><Settings2 className="h-4 w-4" />{zh ? "本轮上下文" : "Turn context"}</div><p className="mt-2 text-xs leading-5 text-text-pg-muted">{zh ? "控制本轮检索范围与回答方式。" : "Control retrieval scope and response behavior for this turn."}</p></div>
        <div className="p-4"><ContextControls locale={locale} dataSources={dataSources} skills={skills} skillCatalog={skillCatalog} customPrompt={customPrompt} attachments={attachments} allowedSources={capabilities?.allowed_data_sources || []} onToggleSource={(value) => toggle(value, dataSources, setDataSources)} onToggleSkill={(value) => toggle(value, skills, setSkills)} onPrompt={setCustomPrompt} onRemoveFile={(name) => setAttachments((current) => current.filter((file) => file.name !== name))} /></div>
      </aside>
    </div>
  );
}

function ContextControls({ locale, dataSources, skills, skillCatalog, customPrompt, attachments, allowedSources, onToggleSource, onToggleSkill, onPrompt, onRemoveFile }: { locale: Locale; dataSources: string[]; skills: string[]; skillCatalog: SkillSummary[]; customPrompt: string; attachments: AgentAttachment[]; allowedSources: string[]; onToggleSource: (value: string) => void; onToggleSkill: (value: string) => void; onPrompt: (value: string) => void; onRemoveFile: (name: string) => void }) {
  const zh = locale === "zh";
  const sourceLabels: Record<string, string> = { market: zh ? "实时行情" : "Live market", rss: "RSS", fintwit: "FinTwit", "x-twitter": "X / Twitter", bloomberg: "Bloomberg", portfolio: zh ? "账户数据" : "Portfolio", options: zh ? "期权" : "Options" };
  const skillLabels: Record<string, string> = { market_research: zh ? "市场研究" : "Market research", news_research: zh ? "新闻检索" : "News research", portfolio_review: zh ? "组合复核" : "Portfolio review", options_analysis: zh ? "期权分析" : "Options analysis", source_check: zh ? "来源核验" : "Source verification", deep_research: zh ? "深度研究" : "Deep research" };
  return <div className="space-y-6">
    <section><div className="mb-2 flex items-center gap-2 text-xs font-semibold"><Database className="h-3.5 w-3.5" />{zh ? "数据" : "Data"}</div><div className="grid grid-cols-2 gap-2">{DATA_SOURCES.map((item) => { const allowed = allowedSources.includes("all") || allowedSources.includes(item) || (item === "x-twitter" && allowedSources.includes("x")); return <button key={item} type="button" disabled={!allowed} onClick={() => onToggleSource(item)} title={!allowed ? (zh ? "当前套餐不可用" : "Upgrade required") : sourceLabels[item]} className={`min-h-9 border px-2 text-left text-[11px] disabled:cursor-not-allowed disabled:opacity-35 ${dataSources.includes(item) ? "border-border-pg-strong bg-bg-panel text-text-pg" : "border-border-pg text-text-pg-dim hover:text-text-pg-muted"}`}>{sourceLabels[item]}{!allowed ? " · Locked" : ""}</button>; })}</div></section>
    <section><div className="mb-2 flex items-center gap-2 text-xs font-semibold"><Sparkles className="h-3.5 w-3.5" />Skills <span className="ml-auto font-normal text-text-pg-dim">Registry</span></div><div className="space-y-1.5">{skillCatalog.map((item) => <label key={item.skill_id} title={item.description} className="flex cursor-pointer items-start gap-2 border border-border-pg px-2.5 py-2 text-xs"><input type="checkbox" checked={skills.includes(item.skill_id)} onChange={() => onToggleSkill(item.skill_id)} className="mt-0.5 accent-white" /><span className="min-w-0 flex-1"><span className="block">{skillLabels[item.slug] || item.name}</span><span className="mt-0.5 block truncate text-[10px] text-text-pg-dim">v{item.current_version} · {item.scope} · {item.risk_level}</span></span></label>)}</div></section>
    <section><label className="mb-2 block text-xs font-semibold">Prompt</label><textarea value={customPrompt} onChange={(event) => onPrompt(event.target.value.slice(0, 2000))} rows={5} placeholder={zh ? "例如：使用简洁中文，先结论后证据，列出反方观点。" : "Example: concise answer, conclusion first, include counter-evidence."} className="w-full resize-y border border-border-pg bg-bg-panel p-2 text-xs leading-5 outline-none focus:border-border-pg-strong" /><div className="mt-1 text-right text-[10px] text-text-pg-dim">{customPrompt.length}/2000</div></section>
    <section><div className="mb-2 flex items-center gap-2 text-xs font-semibold"><FilePlus2 className="h-3.5 w-3.5" />{zh ? "文件" : "Files"}<span className="ml-auto font-normal text-text-pg-dim">{attachments.length}/5</span></div>{attachments.length ? <div className="space-y-1.5">{attachments.map((file) => <div key={file.name} className="flex items-center gap-2 border border-border-pg bg-bg-panel px-2 py-2 text-xs"><span className="min-w-0 flex-1 truncate">{file.name}</span><button type="button" onClick={() => onRemoveFile(file.name)} title={zh ? "移除" : "Remove"}><X className="h-3.5 w-3.5" /></button></div>)}</div> : <p className="text-[11px] leading-5 text-text-pg-dim">{zh ? "支持 TXT、MD、CSV、JSON；单文件 20KB，总计 50KB。" : "TXT, MD, CSV, JSON; 20KB each and 50KB total."}</p>}</section>
  </div>;
}

function StrategyToolResult({ result, locale }: { result: { tool: string; data: Record<string, unknown> }; locale: Locale }) {
  if (!result.tool.includes("strategy") && !result.tool.includes("activation") && !result.tool.includes("order_preview")) return null;
  const zh = locale === "zh";
  const data = result.data;
  const draft = (data.draft || (data.payload as Record<string, unknown> | undefined)?.strategy || {}) as Record<string, unknown>;
  const run = (data.run || {}) as Record<string, unknown>;
  return <section className="border border-border-pg-strong bg-bg-panel p-4 text-sm">
    <div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase text-text-pg-dim">{result.tool}</p><h3 className="mt-1 font-semibold">{String(data.name || (data.intent_type ? `${data.execution_mode} activation` : "Strategy control"))}</h3></div><span className="border border-border-pg px-2 py-1 text-xs">{String(data.status || run.status || "PREVIEW")}</span></div>
    <div className="mt-4 grid gap-3 sm:grid-cols-3"><ToolMetric label={zh ? "版本" : "Version"} value={String(data.current_version || data.strategy_version || run.strategy_version || "-")} /><ToolMetric label={zh ? "模式" : "Mode"} value={String(data.execution_mode || run.execution_mode || draft.execution_mode || "-")} /><ToolMetric label={zh ? "标的" : "Instrument"} value={Array.isArray(draft.instruments) ? draft.instruments.join(", ") : String(data.instrument || "-")} /></div>
    {Array.isArray(draft.sentiment_sources) ? <p className="mt-3 text-xs text-text-pg-muted">{zh ? "数据源" : "Sources"}: {draft.sentiment_sources.join(", ") || "market"}</p> : null}
    {data.confirmation ? <div className="mt-3 border border-status-warning bg-bg-panel-muted p-3"><p className="text-xs text-status-warning">{zh ? "Runtime 尚未启动。下一轮需完整发送：" : "Runtime not started. Send this exact phrase in a new turn:"}</p><code className="mt-2 block overflow-x-auto text-xs">{String(data.confirmation)}</code></div> : null}
  </section>;
}

function ToolMetric({ label, value }: { label: string; value: string }) { return <div><p className="text-xs text-text-pg-dim">{label}</p><p className="mt-1 font-medium">{value}</p></div>; }
