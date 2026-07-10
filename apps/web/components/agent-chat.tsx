"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, CircleStop, ExternalLink, Loader2, MessageSquarePlus, RefreshCw, Send, Wrench } from "lucide-react";
import { ReportMarkdown } from "@/components/puregamma";
import { type Locale, withLocale } from "@/i18n/routing";
import { AgentConversation, AgentMessage, AgentSource, cancelAgentRun, createAgentConversation, getAgentConversation, getAgentConversations, getAgentQuota, getMe, streamAgentMessage } from "@/lib/api";

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
  const [quota, setQuota] = useState<{ remaining: number; limit: number; credit_balance: number } | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
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
    Promise.all([getMe(), loadConversations(), getAgentQuota()])
      .then(async ([, rows, usage]) => {
        if (!active) return;
        setQuota(usage);
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
    setInput("");
    setBusy(true);
    setError("");
    setToolStatus([]);
    followRef.current = true;
    const id = await ensureConversation();
    const now = new Date().toISOString();
    setMessages((current) => [...current, { id: `local-${Date.now()}`, conversation_id: id, role: "user", content, status: "completed", input_tokens: 0, output_tokens: 0, created_at: now, sources: [] }]);
    const controller = new AbortController();
    controllerRef.current = controller;
    let assistantId = "";
    try {
      await streamAgentMessage(id, content, locale, controller.signal, ({ event: eventName, data }) => {
        if (eventName === "run.started") {
          activeRunRef.current = String(data.runId || "");
          assistantId = String(data.messageId || `assistant-${Date.now()}`);
          setMessages((current) => [...current, { id: assistantId, conversation_id: id, role: "assistant", content: "", status: "streaming", input_tokens: 0, output_tokens: 0, created_at: new Date().toISOString(), sources: [] }]);
        } else if (eventName === "message.delta") {
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, content: `${message.content}${String(data.delta || "")}` } : message));
        } else if (eventName === "tool.started") {
          setToolStatus((current) => [...current, `${String(data.tool)} · ${zh ? "检索中" : "retrieving"}`]);
        } else if (eventName === "tool.completed") {
          setToolStatus((current) => current.map((item) => item.startsWith(String(data.tool)) ? `${String(data.tool)} · ${data.error ? (zh ? "失败" : "failed") : (zh ? "完成" : "complete")}` : item));
        } else if (eventName === "citation") {
          const source: AgentSource = { provider: String(data.provider), title: String(data.title), url: data.url ? String(data.url) : null, published_at: data.publishedAt ? String(data.publishedAt) : null, source_timestamp: data.sourceTimestamp ? String(data.sourceTimestamp) : null, fetched_at: String(data.fetchedAt), citation_index: Number(data.index) };
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, sources: [...message.sources, source] } : message));
        } else if (eventName === "message.completed") {
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "completed", input_tokens: Number(data.inputTokens || 0), output_tokens: Number(data.outputTokens || 0) } : message));
        } else if (eventName === "run.failed") {
          setMessages((current) => current.map((message) => message.id === String(data.messageId) ? { ...message, status: "failed", error_code: String(data.code), error_message: String(data.message) } : message));
          setError(String(data.message || (zh ? "Agent 运行失败" : "Agent run failed")));
        }
      });
      const refreshed = await getAgentConversation(id);
      setMessages(refreshed.messages);
      await loadConversations();
      setQuota(await getAgentQuota());
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

  return (
    <div className="grid min-h-[calc(100vh-8rem)] overflow-hidden border border-border-pg bg-bg-panel lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="border-b border-border-pg bg-bg-app lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between border-b border-border-pg p-3">
          <div><div className="text-xs uppercase text-text-pg-dim">PureGamma Agent</div><div className="mt-1 text-xs text-text-pg-muted">{quota ? `${quota.remaining}/${quota.limit} ${zh ? "今日剩余" : "remaining"}` : "-"}</div></div>
          <button type="button" onClick={createNew} className="grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong" title={zh ? "新会话" : "New conversation"}><MessageSquarePlus className="h-4 w-4" /></button>
        </div>
        <div className="flex gap-2 overflow-x-auto p-2 lg:block lg:max-h-[calc(100vh-13rem)] lg:space-y-1 lg:overflow-y-auto">
          {conversations.map((conversation) => <button key={conversation.id} type="button" onClick={() => { router.push(withLocale(locale, `/chat/${conversation.id}`)); openConversation(conversation.id); }} className={`min-w-52 border px-3 py-2 text-left text-sm lg:block lg:w-full lg:min-w-0 ${conversation.id === conversationId ? "border-border-pg-strong bg-bg-panel-muted" : "border-transparent text-text-pg-muted hover:border-border-pg"}`}><div className="truncate font-medium">{conversation.title}</div><div className="mt-1 text-xs text-text-pg-dim">{new Date(conversation.updated_at).toLocaleDateString(locale)}</div></button>)}
        </div>
      </aside>

      <section className="flex min-h-[70vh] min-w-0 flex-col">
        <div ref={scrollRef} onScroll={(event) => { const target = event.currentTarget; followRef.current = target.scrollHeight - target.scrollTop - target.clientHeight < 120; }} className="flex-1 overflow-y-auto p-4 md:p-6">
          {loading ? <div className="grid min-h-64 place-items-center"><Loader2 className="h-5 w-5 animate-spin" /></div> : null}
          {!loading && messages.length === 0 ? <div className="mx-auto grid min-h-[50vh] max-w-xl place-items-center text-center"><div><Bot className="mx-auto h-7 w-7 text-text-pg-muted" /><h1 className="mt-4 text-xl font-semibold">{zh ? "开始一项市场研究" : "Start a market research thread"}</h1><p className="mt-2 text-sm leading-6 text-text-pg-muted">{zh ? "询问 BTC、DeFi、链上状态或最近新闻。回答只使用已经同步并带时间戳的数据。" : "Ask about BTC, DeFi, chain status, or recent news. Answers use synchronized, timestamped evidence only."}</p></div></div> : null}
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((message) => <div key={message.id} className={message.role === "user" ? "ml-auto max-w-[85%] border border-border-pg-strong bg-bg-panel-muted p-3 text-sm" : "max-w-full border-l border-border-pg pl-4"}>
              {message.role === "assistant" ? <ReportMarkdown content={message.content || (message.status === "streaming" ? (zh ? "正在分析..." : "Analyzing...") : "")} locale={locale} /> : <p className="whitespace-pre-wrap leading-6">{message.content}</p>}
              {message.status === "failed" ? <div className="mt-3 border border-status-negative p-3 text-sm text-status-negative"><p>{message.error_message}</p><button type="button" onClick={() => { setInput(messages.find((item) => item.role === "user" && item.created_at <= message.created_at)?.content || ""); }} className="mt-2 inline-flex items-center gap-2 border border-border-pg px-2 py-1"><RefreshCw className="h-3.5 w-3.5" />{zh ? "重试" : "Retry"}</button></div> : null}
              {message.sources.length ? <div className="mt-4 border-t border-border-pg pt-3"><div className="mb-2 text-xs font-semibold uppercase text-text-pg-muted">{zh ? "来源" : "Sources"}</div><div className="grid gap-2 sm:grid-cols-2">{message.sources.map((source) => <div key={`${message.id}-${source.citation_index}`} className="min-w-0 border border-border-pg bg-bg-panel-muted p-2 text-xs"><div className="flex items-start gap-2"><span className="text-text-pg-dim">[{source.citation_index}]</span><div className="min-w-0"><div className="truncate font-medium">{source.title}</div><div className="mt-1 text-text-pg-dim">{source.provider} · {new Date(source.source_timestamp || source.fetched_at).toLocaleString(locale)}</div>{source.url ? <Link href={source.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-text-pg-muted hover:text-text-pg">{zh ? "打开来源" : "Open source"}<ExternalLink className="h-3 w-3" /></Link> : null}</div></div></div>)}</div></div> : null}
            </div>)}
            {toolStatus.length ? <div className="flex flex-wrap gap-2">{toolStatus.map((item) => <span key={item} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs text-text-pg-muted"><Wrench className="h-3 w-3" />{item}</span>)}</div> : null}
          </div>
        </div>
        <div className="border-t border-border-pg bg-bg-app p-3 md:p-4">
          <form onSubmit={send} className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} rows={2} placeholder={zh ? "输入研究问题..." : "Ask a research question..."} className="min-h-14 flex-1 resize-none border border-border-pg bg-bg-panel px-3 py-2 text-sm outline-none focus:border-border-pg-strong" />
            {busy ? <button type="button" onClick={stop} className="grid h-14 w-12 place-items-center border border-border-pg text-status-negative" title={zh ? "停止生成" : "Stop generation"}><CircleStop className="h-5 w-5" /></button> : <button type="submit" disabled={!input.trim()} className="grid h-14 w-12 place-items-center border border-border-pg-strong bg-pg-white text-pg-black disabled:opacity-40" title={zh ? "发送" : "Send"}><Send className="h-5 w-5" /></button>}
          </form>
          {error ? <p className="mx-auto mt-2 max-w-3xl text-xs text-status-negative">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
