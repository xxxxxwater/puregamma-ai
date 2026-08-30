"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Clock3, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { getNewsFeed, type NewsFeedItem, type NewsFeedResponse } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

type Copy = {
  live: string;
  autoRefresh: string;
  lastSync: string;
  filters: {
    content: string;
    source: string;
    asset: string;
    window: string;
    all: string;
    flash: string;
    articles: string;
    allSources: string;
    chaincatcher: string;
    otherRss: string;
    allAssets: string;
    hours24: string;
    hours72: string;
    days7: string;
  };
  searchPlaceholder: string;
  search: string;
  clear: string;
  loading: string;
  loadingMore: string;
  loadMore: string;
  emptyTitle: string;
  emptyDescription: string;
  errorTitle: string;
  retry: string;
  original: string;
  flashLabel: string;
  articleLabel: string;
  openSource: string;
  justNow: string;
  minutesAgo: string;
  hoursAgo: string;
  daysAgo: string;
  disclaimer: string;
  latency: string;
  languageFallback: string;
  headline: string;
  askAgent: string;
};

type Filters = {
  kind: "all" | "flash" | "article";
  source: "all" | "chaincatcher" | "rss";
  symbol: string;
  hours: number;
  q: string;
};

const assets = ["BTC", "ETH", "SOL", "HYPE"];

function uniqueItems(items: NewsFeedItem[]): NewsFeedItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function preciseTime(item: NewsFeedItem, locale: Locale): string {
  const date = new Date(item.published_at);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", sameDay ? { hour: "2-digit", minute: "2-digit", hour12: false } : { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function askAgentHref(item: NewsFeedItem, locale: Locale): string {
  return `/${locale}/chat?topic=${encodeURIComponent(item.title)}`;
}

function relativeTime(item: NewsFeedItem, copy: Copy): string {
  const seconds = Math.max(0, item.age_seconds);
  if (seconds < 60) return copy.justNow;
  if (seconds < 3600) return copy.minutesAgo.replace("{count}", String(Math.floor(seconds / 60)));
  if (seconds < 86400) return copy.hoursAgo.replace("{count}", String(Math.floor(seconds / 3600)));
  return copy.daysAgo.replace("{count}", String(Math.floor(seconds / 86400)));
}

function FilterButton({ active, children, onClick }: { active: boolean; children: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${active ? "border-border-pg-strong bg-pg-white text-pg-black" : "border-border-pg bg-bg-panel text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"}`}
    >
      {children}
    </button>
  );
}

export function NewsFeed({ locale, initial, copy }: { locale: Locale; initial: NewsFeedResponse; copy: Copy }) {
  const [feed, setFeed] = useState(initial);
  const [filters, setFilters] = useState<Filters>({ kind: "flash", source: "chaincatcher", symbol: "", hours: 72, q: "" });
  const [draftQuery, setDraftQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(initial.unavailable ? initial.error_code || "UNAVAILABLE" : "");

  const request = useCallback(async (mode: "reset" | "append" | "refresh", cursor?: string) => {
    if (mode === "append") setLoadingMore(true);
    else if (mode === "reset") setLoading(true);
    try {
      const result = await getNewsFeed(locale, {
        kind: filters.kind,
        source: filters.source,
        language: locale,
        symbol: filters.symbol || undefined,
        q: filters.q || undefined,
        hours: filters.hours,
        limit: 30,
        cursor
      });
      if (result.unavailable) {
        setError(result.error_code || "UNAVAILABLE");
        return;
      }
      setError("");
      setFeed((current) => {
        if (mode === "append") return { ...result, items: uniqueItems([...current.items, ...result.items]) };
        if (mode === "refresh") return { ...result, items: uniqueItems([...result.items, ...current.items]).slice(0, 150), page: current.page };
        return result;
      });
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [filters, locale]);

  useEffect(() => {
    void request("reset");
  }, [request]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void request("refresh");
    }, Math.max(30, feed.meta.refresh_after_seconds || 60) * 1000);
    return () => window.clearInterval(interval);
  }, [feed.meta.refresh_after_seconds, request]);

  const lastSync = useMemo(() => {
    if (!feed.meta.last_success_at) return "—";
    return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(feed.meta.last_success_at));
  }, [feed.meta.last_success_at, locale]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setFilters((current) => ({ ...current, q: draftQuery.trim() }));
  }

  function clearSearch() {
    setDraftQuery("");
    setFilters((current) => ({ ...current, q: "" }));
  }

  function setSource(source: Filters["source"]) {
    setFilters((value) => {
      // "其他 RSS" 只含文章：切到 RSS 时若内容仍为"快讯"，自动切到"全部"避免空列表。
      const kind = source === "rss" && value.kind === "flash" ? "all" : value.kind;
      return { ...value, source, kind };
    });
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-border-pg bg-bg-panel p-4 md:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-pg pb-4">
          <div className="flex flex-wrap items-center gap-3 text-xs text-text-pg-muted">
            <span className="inline-flex items-center gap-2 font-semibold text-status-positive"><span className="h-2 w-2 rounded-full bg-status-positive" />{copy.live}</span>
            <span className="inline-flex items-center gap-1.5"><RefreshCw className="h-3.5 w-3.5" />{copy.autoRefresh}</span>
            <span>{copy.lastSync}: {lastSync}</span>
          </div>
          <span className="rounded-full border border-border-pg px-2.5 py-1 text-[0.68rem] text-text-pg-muted">{copy.latency}</span>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[auto_auto_auto_auto_1fr] xl:items-end">
          <div><div className="mb-2 text-[0.66rem] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{copy.filters.content}</div><div className="flex flex-wrap gap-2">
            <FilterButton active={filters.kind === "flash"} onClick={() => setFilters((value) => ({ ...value, kind: "flash" }))}>{copy.filters.flash}</FilterButton>
            <FilterButton active={filters.kind === "article"} onClick={() => setFilters((value) => ({ ...value, kind: "article" }))}>{copy.filters.articles}</FilterButton>
            <FilterButton active={filters.kind === "all"} onClick={() => setFilters((value) => ({ ...value, kind: "all" }))}>{copy.filters.all}</FilterButton>
          </div></div>
          <div><div className="mb-2 text-[0.66rem] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{copy.filters.source}</div><div className="flex flex-wrap gap-2">
            <FilterButton active={filters.source === "chaincatcher"} onClick={() => setSource("chaincatcher")}>{copy.filters.chaincatcher}</FilterButton>
            <FilterButton active={filters.source === "rss"} onClick={() => setSource("rss")}>{copy.filters.otherRss}</FilterButton>
            <FilterButton active={filters.source === "all"} onClick={() => setSource("all")}>{copy.filters.allSources}</FilterButton>
          </div></div>
          <div><div className="mb-2 text-[0.66rem] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{copy.filters.asset}</div><div className="flex flex-wrap gap-2">
            <FilterButton active={!filters.symbol} onClick={() => setFilters((value) => ({ ...value, symbol: "" }))}>{copy.filters.allAssets}</FilterButton>
            {assets.map((asset) => <FilterButton key={asset} active={filters.symbol === asset} onClick={() => setFilters((value) => ({ ...value, symbol: asset }))}>{asset}</FilterButton>)}
          </div></div>
          <div><div className="mb-2 text-[0.66rem] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{copy.filters.window}</div><div className="flex flex-wrap gap-2">
            <FilterButton active={filters.hours === 24} onClick={() => setFilters((value) => ({ ...value, hours: 24 }))}>{copy.filters.hours24}</FilterButton>
            <FilterButton active={filters.hours === 72} onClick={() => setFilters((value) => ({ ...value, hours: 72 }))}>{copy.filters.hours72}</FilterButton>
            <FilterButton active={filters.hours === 168} onClick={() => setFilters((value) => ({ ...value, hours: 168 }))}>{copy.filters.days7}</FilterButton>
          </div></div>
          <form onSubmit={submitSearch} className="flex min-w-0 gap-2 xl:justify-self-end">
            <label className="relative min-w-0 flex-1 xl:w-72"><span className="sr-only">{copy.searchPlaceholder}</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-pg-dim" /><input value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} maxLength={100} placeholder={copy.searchPlaceholder} className="h-9 w-full rounded-lg border border-border-pg bg-bg-app pl-9 pr-3 text-sm outline-none focus:border-border-pg-strong" /></label>
            <button type="submit" className="h-9 rounded-lg border border-border-pg-strong bg-pg-white px-3 text-xs font-semibold text-pg-black">{copy.search}</button>
            {filters.q ? <button type="button" onClick={clearSearch} className="h-9 rounded-lg border border-border-pg px-3 text-xs text-text-pg-muted">{copy.clear}</button> : null}
          </form>
        </div>
      </section>

      <div aria-live="polite" aria-busy={loading} className="space-y-3">
        {feed.meta.language_fallback ? <div className="rounded-xl border border-status-warning/40 bg-bg-panel px-4 py-3 text-sm text-text-pg-muted">{copy.languageFallback}</div> : null}
        {error ? <div className="rounded-xl border border-status-negative/40 bg-bg-panel p-5"><strong>{copy.errorTitle}</strong><div className="mt-3"><button type="button" onClick={() => void request("reset")} className="rounded-lg border border-border-pg px-3 py-2 text-sm">{copy.retry}</button></div></div> : null}
        {loading && !feed.items.length ? <div className="rounded-xl border border-border-pg bg-bg-panel p-8 text-center text-sm text-text-pg-muted">{copy.loading}</div> : null}
        {!loading && !error && !feed.items.length ? <div className="rounded-xl border border-dashed border-border-pg bg-bg-panel p-10 text-center"><Clock3 className="mx-auto h-6 w-6 text-text-pg-dim" /><h2 className="mt-3 font-semibold">{copy.emptyTitle}</h2><p className="mt-2 text-sm text-text-pg-muted">{copy.emptyDescription}</p></div> : null}
        {feed.items.length > 0 ? (
          <div className="space-y-8">
            {(() => {
              const top = feed.items[0];
              return (
                <section className="rounded-2xl border border-border-pg-strong bg-bg-panel p-5 md:p-6">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded bg-status-positive/15 px-2 py-0.5 font-semibold text-status-positive">{copy.headline}</span>
                    <span className="font-medium text-text-pg">{top.attribution}</span>
                    <time dateTime={top.published_at} className="text-text-pg-dim">{relativeTime(top, copy)}</time>
                  </div>
                  <h2 className="mt-2 text-xl font-semibold leading-7 text-text-pg md:text-2xl">
                    {top.url ? <a href={top.url} target="_blank" rel="noopener noreferrer nofollow" className="outline-none hover:underline focus-visible:underline">{top.title}</a> : top.title}
                  </h2>
                  {top.summary ? <p className="mt-2 line-clamp-3 text-sm leading-6 text-text-pg-muted">{top.summary}</p> : null}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {top.symbols.map((symbol) => <span key={symbol} className="rounded-md border border-border-pg bg-bg-app px-2 py-0.5 text-[0.68rem] font-medium">{symbol}</span>)}
                    <a href={askAgentHref(top, locale)} className="text-xs font-medium text-text-pg-muted underline-offset-2 hover:text-text-pg hover:underline">{copy.askAgent}</a>
                  </div>
                </section>
              );
            })()}

            <ol className="relative ml-2 space-y-8 border-l-2 border-border-pg">
              {feed.items.slice(1).map((item) => (
                <li key={item.id} className="group relative ml-6">
                  <span className="absolute -left-[31px] top-1 h-3 w-3 rounded-full border-2 border-border-pg-strong bg-bg-panel ring-4 ring-bg-app" />
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <time dateTime={item.published_at} className="font-mono text-xs text-text-pg-dim">{preciseTime(item, locale)}</time>
                    <span className="text-[0.68rem] font-medium text-text-pg">{item.attribution}</span>
                    <span className="rounded border border-border-pg px-1.5 py-0.5 text-[0.62rem] uppercase tracking-wide text-text-pg-muted">{item.kind === "flash" ? copy.flashLabel : copy.articleLabel}</span>
                    {item.original ? <span className="rounded-full border border-border-pg px-2 py-0.5 text-[0.62rem] text-text-pg-muted">{copy.original}</span> : null}
                  </div>
                  <h3 className="mt-1 text-[0.95rem] font-semibold leading-6 text-text-pg">
                    {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer nofollow" className="outline-none hover:underline focus-visible:underline">{item.title}</a> : item.title}
                  </h3>
                  {item.summary ? <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-pg-muted">{item.summary}</p> : null}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {item.symbols.map((symbol) => <span key={symbol} className="rounded-md border border-border-pg bg-bg-app px-2 py-0.5 text-[0.66rem] font-medium">{symbol}</span>)}
                    <a href={askAgentHref(item, locale)} className="text-[0.68rem] font-medium text-text-pg-dim underline-offset-2 hover:text-text-pg hover:underline">{copy.askAgent}</a>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </div>

      {feed.page.has_more && feed.page.next_cursor ? <button type="button" disabled={loadingMore} onClick={() => void request("append", feed.page.next_cursor || undefined)} className="w-full rounded-xl border border-border-pg bg-bg-panel py-3 text-sm font-medium hover:border-border-pg-strong disabled:opacity-50">{loadingMore ? copy.loadingMore : copy.loadMore}</button> : null}

      <div className="flex gap-2 rounded-xl border border-border-pg bg-bg-panel p-4 text-xs leading-5 text-text-pg-muted"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /><p>{copy.disclaimer}</p></div>
    </div>
  );
}
