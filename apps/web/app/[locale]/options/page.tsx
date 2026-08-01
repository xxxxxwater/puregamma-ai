import type { Metadata } from "next";
import { ExternalLink, Gauge, ShieldCheck, TrendingUp } from "lucide-react";

import { Badge, DataSourceStatusBadge, MetricCard, PageHeader, ResearchCard } from "@/components/puregamma";
import { PGTable } from "@/components/pg-table";
import { getEarningsGamma, getLongGammaCandidates } from "@/lib/api";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const zh = params.locale === "zh";
  return {
    title: zh ? "Deribit 期权研究 | PureGamma AI" : "Deribit Options Research | PureGamma AI",
    description: zh ? "实时期权链、Greeks 与 Long Gamma 研究。" : "Live option chains, Greeks, and long gamma research."
  };
}

export default async function OptionsPage({ params, searchParams }: { params: { locale: Locale }; searchParams: { currency?: string } }) {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  const currency = searchParams.currency === "ETH" ? "ETH" : "BTC";
  const gamma = await getLongGammaCandidates(currency);
  const earnings = await getEarningsGamma(locale);
  const metric = gamma.candidates[0];

  return <div className="space-y-5">
    <PageHeader eyebrow="DERIBIT OPTIONS" title={zh ? "期权与 Long Gamma 研究" : "Options and Long Gamma Research"} description={zh ? "基于 Deribit 公开行情的只读期权研究。AI 负责排序与解释，Greeks 和价格均来自真实接口。" : "Read-only options research from Deribit public market data. AI ranks and explains; prices and Greeks come from the live source."} sectionNumber="04" />

    <div className="flex flex-wrap items-center justify-between gap-3 border-y border-border-pg py-3">
      <div className="flex gap-2">
        {(["BTC", "ETH"] as const).map((item) => <a key={item} href={`?currency=${item}`} className={`border px-3 py-2 text-sm ${currency === item ? "border-border-pg-strong bg-bg-panel-muted" : "border-border-pg text-text-pg-muted"}`}>{item}</a>)}
      </div>
      <div className="flex items-center gap-2"><DataSourceStatusBadge locale={locale} status={gamma.status} /><Badge tone="neutral">READ ONLY</Badge></div>
    </div>

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label={zh ? "期权合约" : "Option instruments"} value={String(gamma.instrument_count)} tone="cyan" />
      <MetricCard label={zh ? "候选数量" : "Candidates"} value={String(gamma.candidates.length)} tone="cyan" />
      <MetricCard label={zh ? "最高研究分" : "Top research score"} value={metric ? metric.research_score.toFixed(1) : "-"} tone="amber" />
      <MetricCard label={zh ? "数据源" : "Source"} value="Deribit Public" tone="neutral" />
    </section>

    {gamma.error ? <div className="border border-status-warning p-4 text-sm text-status-warning">{gamma.error}</div> : null}

    <ResearchCard>
      <div className="mb-4 flex items-start justify-between gap-3"><div><h2 className="flex items-center gap-2 font-semibold"><Gauge className="h-4 w-4" />Long Gamma {zh ? "候选" : "candidates"} — {currency}</h2><p className="mt-2 text-sm text-text-pg-muted">{zh ? "综合正 Gamma、Theta 成本、价差、成交量、OI 与到期时间排序。" : "Ranked by positive gamma, theta cost, spread, volume, OI, and time to expiry."}</p></div><ShieldCheck className="h-5 w-5 text-status-positive" /></div>
      <PGTable minWidth={960} empty={<p className="text-sm text-text-pg-muted">{zh ? "当前没有满足数据完整性与流动性要求的候选。" : "No candidates currently satisfy data completeness and liquidity requirements."}</p>} columns={[{ key: "instrument", header: zh ? "合约" : "Instrument", render: (item: typeof gamma.candidates[number]) => <span className="font-semibold">{item.instrument}</span> }, { key: "score", header: zh ? "评分" : "Score", render: (item: typeof gamma.candidates[number]) => item.research_score.toFixed(1) }, { key: "iv", header: "IV", render: (item: typeof gamma.candidates[number]) => format(item.mark_iv) }, { key: "delta", header: "Delta", render: (item: typeof gamma.candidates[number]) => format(item.greeks.delta, 4) }, { key: "gamma", header: "Gamma", render: (item: typeof gamma.candidates[number]) => format(item.greeks.gamma, 6) }, { key: "theta", header: "Theta", render: (item: typeof gamma.candidates[number]) => format(item.greeks.theta, 4) }, { key: "spread", header: zh ? "价差" : "Spread", render: (item: typeof gamma.candidates[number]) => item.spread_pct != null ? `${(item.spread_pct * 100).toFixed(2)}%` : "-" }, { key: "oi", header: "OI", render: (item: typeof gamma.candidates[number]) => item.open_interest.toLocaleString(locale) }, { key: "dte", header: zh ? "剩余天数" : "DTE", render: (item: typeof gamma.candidates[number]) => item.days_to_expiry }]} rows={gamma.candidates} />
    </ResearchCard>

    <ResearchCard>
      <div className="mb-4 flex items-start justify-between gap-3"><div><h2 className="flex items-center gap-2 font-semibold"><TrendingUp className="h-4 w-4" />Long Gamma {zh ? "美股候选" : "US Stock Candidates"} — {zh ? "财报季" : "Earnings"}</h2><p className="mt-2 text-sm text-text-pg-muted">{zh ? "未来一周公布财报的美股标的，综合标的情绪、新闻覆盖与波动性排序。每个美股交易日自动刷新。" : "US stocks with upcoming earnings in the next week, ranked by sentiment, news coverage, and volatility. Auto-refreshed every US market day."}</p></div><ShieldCheck className="h-5 w-5 text-status-positive" /></div>
      <PGTable minWidth={800} empty={<p className="text-sm text-text-pg-muted">{zh ? "暂无财报候选。数据将在下一个美股交易日自动刷新。" : "No earnings candidates. Data refreshes on the next US market day."}</p>} columns={[{ key: "symbol", header: zh ? "标的" : "Symbol", render: (item: typeof earnings.candidates[number]) => <span className="font-semibold">{item.symbol}</span> }, { key: "name", header: zh ? "名称" : "Name", render: (item: typeof earnings.candidates[number]) => <span className="text-text-pg-muted">{item.name}</span> }, { key: "score", header: zh ? "评分" : "Score", render: (item: typeof earnings.candidates[number]) => item.research_score.toFixed(1) }, { key: "sector", header: zh ? "行业" : "Sector", render: (item: typeof earnings.candidates[number]) => item.sector }, { key: "cap", header: zh ? "市值" : "Cap", render: (item: typeof earnings.candidates[number]) => item.market_cap_category }, { key: "earnings", header: zh ? "财报日期" : "Earnings", render: (item: typeof earnings.candidates[number]) => item.earnings_date || "-" }, { key: "news", header: zh ? "关联新闻" : "News", render: (item: typeof earnings.candidates[number]) => <span className="max-w-[240px] truncate text-text-pg-dim">{item.news_snippet || "-"}</span> }]} rows={earnings.candidates} />
    </ResearchCard>

    <div className="flex flex-wrap items-center justify-between gap-3 border border-border-pg bg-bg-panel-muted p-4 text-xs text-text-pg-muted"><span>{zh ? "研究排序不是收益承诺；最大损失、Theta 衰减、流动性和到期风险需要独立评估。" : "Research ranking is not a return promise. Maximum loss, theta decay, liquidity, and expiry risk require independent review."}</span>{gamma.source_url ? <a className="inline-flex items-center gap-1 text-text-pg" href={gamma.source_url} target="_blank" rel="noreferrer">Deribit API <ExternalLink className="h-3.5 w-3.5" /></a> : null}</div>
  </div>;
}

function format(value?: number | null, digits = 2) { return value == null ? "-" : value.toFixed(digits); }
