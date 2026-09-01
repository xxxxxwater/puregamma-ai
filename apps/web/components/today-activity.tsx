"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Bot, BriefcaseBusiness, FlaskConical } from "lucide-react";
import { CapabilityGate, useCapabilityGate } from "@/components/ocean/capability-gate";
import { StatusBadge } from "@/components/ocean/status-badge";
import { getAgentConversations, getGlobalMarket, getPortfolioSnapshot, getResearchRuns, type AgentConversation, type HarnessResearchRun, type PortfolioSnapshot } from "@/lib/api";
import { type Locale, withLocale } from "@/i18n/routing";

function formatTime(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

type Zone = { key: string; step: string; icon: typeof Bot; en: string; zh: string; href: string; hrefLabelEn: string; hrefLabelZh: string };

// Decision order: Agent (exploration) -> Research (capability-gated) -> Portfolio (calm, no ocean).
const ZONES: Zone[] = [
  { key: "agent", step: "01", icon: Bot, en: "Agent Activity", zh: "Agent 动态", href: "/chat", hrefLabelEn: "Continue", hrefLabelZh: "继续对话" },
  { key: "research", step: "02", icon: FlaskConical, en: "Research Activity", zh: "研究动态", href: "/research", hrefLabelEn: "Workbench", hrefLabelZh: "研究台" },
  { key: "portfolio", step: "03", icon: BriefcaseBusiness, en: "Portfolio Snapshot", zh: "组合快照", href: "/portfolio", hrefLabelEn: "Details", hrefLabelZh: "详情" },
];

/**
 * Today's decision timeline on the dashboard. Agent (exploration), Research
 * (capability-gated) and Portfolio (calm) are presented as ordered decision
 * steps of the day; every link, capability gate, empty/error and stale state
 * is preserved. The panels use the liquid glass surface (Glass mode only).
 */
export function TodayActivity({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [liveTrading, setLiveTrading] = useState<boolean | "unknown" | null>(null);
  const researchGate = useCapabilityGate(() => getResearchRuns(5, 0), []);
  const [recentRuns, setRecentRuns] = useState<HarnessResearchRun[]>([]);

  useEffect(() => {
    let cancelled = false;
    getAgentConversations().then((payload: { conversations: AgentConversation[] }) => { if (!cancelled) setConversations(payload.conversations.slice(0, 4)); }).catch(() => undefined);
    getPortfolioSnapshot(locale).then((payload: PortfolioSnapshot) => { if (!cancelled) setPortfolio(payload); }).catch(() => undefined);
    getGlobalMarket(locale).then((payload) => { if (!cancelled) setLiveTrading(payload.unavailable ? "unknown" : Boolean(payload.live_trading)); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [locale]);

  useEffect(() => {
    if (researchGate.state.status !== "available") return;
    let cancelled = false;
    getResearchRuns(5, 0).then((payload) => { if (!cancelled) setRecentRuns(payload.runs || []); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [researchGate.state.status]);

  const nav = (portfolio?.nav ?? 0) >= 0 ? (portfolio?.nav ?? 0) : 0;
  const portfolioStale = Boolean(portfolio?.stale);

  return (
    <div className="chrono-decision-stream" data-chrono-slice>
      <div className="mb-4 flex items-center gap-3 overflow-x-auto pb-1">
        {ZONES.map((zone) => (
          <div key={zone.key} className="group flex shrink-0 items-center gap-2">
            <span className="text-[0.62rem] font-semibold tabular-nums text-text-pg-dim">{zone.step}</span>
            <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{zh ? zone.zh : zone.en}</span>
            <span aria-hidden className="h-px w-8 bg-border-pg" />
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr_0.9fr]">
        <section className="terminal-panel">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold"><Bot className="h-4 w-4 text-ocean-cyan" aria-hidden />{zh ? "Agent 动态" : "Agent Activity"}</h2>
            <Link href={withLocale(locale, "/chat")} className="inline-flex items-center gap-1 text-xs text-text-pg-muted hover:text-text-pg">{zh ? "继续对话" : "Continue"}<ArrowRight className="h-3 w-3" aria-hidden /></Link>
          </div>
          {conversations.length === 0 ? (
            <p className="text-sm text-text-pg-muted">{zh ? "还没有 Agent 会话。开始一次对话，研究问题、策略或风险。" : "No Agent conversations yet. Start one to research a question, strategy, or risk."}</p>
          ) : (
            <ul className="space-y-2">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <Link href={withLocale(locale, `/chat/${conversation.id}`)} className="group flex items-center justify-between gap-3 border border-transparent px-2 py-1.5 transition hover:border-border-pg rounded-lg">
                    <span className="min-w-0 truncate text-sm text-text-pg">{conversation.title}</span>
                    <span className="shrink-0 text-xs text-text-pg-dim">{formatTime(conversation.updated_at, locale)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="terminal-panel">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold"><FlaskConical className="h-4 w-4 text-ocean-violet" aria-hidden />{zh ? "研究动态" : "Research Activity"}</h2>
            <Link href={withLocale(locale, "/research")} className="inline-flex items-center gap-1 text-xs text-text-pg-muted hover:text-text-pg">{zh ? "研究台" : "Workbench"}<ArrowRight className="h-3 w-3" aria-hidden /></Link>
          </div>
          <CapabilityGate state={researchGate.state} locale={locale} onRetry={researchGate.retry}>
            {recentRuns.length === 0 ? (
              <p className="text-sm text-text-pg-muted">{zh ? "还没有研究任务。" : "No research runs yet."}</p>
            ) : (
              <ul className="space-y-2">
                {recentRuns.map((run) => (
                  <li key={run.id}>
                    <Link href={withLocale(locale, `/research/${run.id}`)} className="group flex items-center justify-between gap-3 border border-transparent px-2 py-1.5 transition hover:border-border-pg rounded-lg">
                      <span className="min-w-0 truncate text-sm text-text-pg">{run.name || run.id}</span>
                      <span className="flex shrink-0 items-center gap-2">
                        <StatusBadge domain="research" value={run.status} locale={locale} />
                        <span className="text-xs text-text-pg-dim">{formatTime(run.updated_at, locale)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CapabilityGate>
        </section>

        <section className="terminal-panel">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold"><BriefcaseBusiness className="h-4 w-4" aria-hidden />{zh ? "组合快照" : "Portfolio Snapshot"}</h2>
            <Link href={withLocale(locale, "/portfolio")} className="inline-flex items-center gap-1 text-xs text-text-pg-muted hover:text-text-pg">{zh ? "详情" : "Details"}<ArrowRight className="h-3 w-3" aria-hidden /></Link>
          </div>
          <div className="tabular-nums">
            <div className="text-2xl font-semibold text-text-pg">${nav.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            <div className="mt-1 text-xs text-text-pg-muted">
              {zh ? "净值 (NAV)" : "Net asset value"}
              {portfolio?.data_as_of ? <> · {zh ? "更新于" : "as of"} {formatTime(portfolio.data_as_of, locale)}</> : null}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {liveTrading === "unknown" ? <StatusBadge domain="data" value="unknown" locale={locale} /> : liveTrading === null ? null : <StatusBadge domain="trading" value={liveTrading ? "LIVE" : "LIVE_DISABLED"} locale={locale} />}
            {portfolioStale ? <StatusBadge domain="data" value="stale" locale={locale} /> : null}
            {!portfolioStale && portfolio?.connected ? <StatusBadge domain="data" value="fresh" locale={locale} /> : null}
          </div>
          {portfolioStale ? (
            <p className="mt-2 text-xs leading-5 text-status-warning">{zh ? "数据已过期：NAV 可能未反映最新市场价格。请在组合页同步账户。" : "Data is stale: NAV may not reflect the latest market prices. Sync your account on the Portfolio page."}</p>
          ) : null}
          {!portfolio?.connected ? <p className="mt-2 text-xs leading-5 text-text-pg-muted">{zh ? "尚未连接任何投资账户。" : "No investment account connected yet."}</p> : null}
        </section>
      </div>
    </div>
  );
}