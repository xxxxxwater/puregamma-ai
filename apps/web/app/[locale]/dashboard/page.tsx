import type { Metadata } from "next";
import { Activity, BellRing, CreditCard, Database, LineChart, Radio } from "lucide-react";
import { getDashboard, fallbackDataSourcesForLocale } from "@/lib/api";
import { ActionLink, Badge, DataSourceStatusBadge, DiligenceLedger, MarketRegimeBanner, MetricCard, MockModeBadge, PageHeader, ProcessStepper, ResearchCard, RiskBadge, SignalTable } from "@/components/puregamma";
import { Markdown } from "@/components/markdown";
import { formatCurrency, formatDateTime } from "@/lib/formatters";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "dashboard", "/dashboard");
}

export default async function DashboardPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "dashboard");
  const { market, subscription, reports, signals, mockMode } = await getDashboard(locale);
  const latest = reports.reports[0];
  const signalRows = signals.signals;
  const confidenceRows = signalRows.slice(0, 4).map((signal) => ({ ...signal, confidencePct: Math.round(signal.confidence * 100) }));
  const dataSources = fallbackDataSourcesForLocale(locale);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="00"
        actions={<><MockModeBadge locale={locale} live={!mockMode} /><ActionLink href={withLocale(locale, "/reports")}>{t(locale, "common.actions.openResearchLibrary")}</ActionLink></>}
      />

      <MarketRegimeBanner locale={locale} regime={copy.marketRegime.regime} freshness={mockMode ? t(locale, "common.shared.demoSnapshot") : t(locale, "common.topbar.freshness")} summary={copy.marketRegime.summary} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label={copy.metrics.totalNav} value={formatCurrency(locale, 1284200, true)} detail={copy.metrics.partialPortfolioData} tone="cyan" icon={<LineChart className="h-4 w-4" />} />
        <MetricCard label={copy.metrics.dailyPnl} value="+$18.2K" detail={copy.metrics.simulated} tone="emerald" icon={<Activity className="h-4 w-4" />} />
        <MetricCard label={copy.metrics.creditBalance} value={String(subscription.credit_balance)} detail={`${subscription.plan} plan`} tone="cyan" icon={<CreditCard className="h-4 w-4" />} />
        <MetricCard label={copy.metrics.activeSignals} value={String(signalRows.length)} detail={copy.metrics.activeResearchSignals} tone="emerald" icon={<Radio className="h-4 w-4" />} />
        <MetricCard label={copy.metrics.dataHealth} value="83%" detail={copy.metrics.dataKeys} tone="amber" icon={<Database className="h-4 w-4" />} />
        <MetricCard label={copy.metrics.imessage} value={subscription.entitlement.imessage ? copy.metrics.enabled : copy.metrics.restricted} detail="Max / Enterprise" tone={subscription.entitlement.imessage ? "emerald" : "amber"} icon={<BellRing className="h-4 w-4" />} />
      </div>

      <ProcessStepper steps={copy.process} />

      <section>
        <div className="mb-3 text-eyebrow uppercase text-text-pg-muted">{copy.assetMonitor.title}</div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {market.assets.map((asset) => (
            <ResearchCard key={asset.symbol} className="flex min-h-[238px] flex-col">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-xl font-semibold">{asset.symbol}</div>
                    <Badge tone={asset.is_realtime ? "emerald" : "amber"}>{asset.is_realtime ? copy.assetMonitor.liveRest : copy.assetMonitor.fallback}</Badge>
                  </div>
                  <div className="mt-3 text-3xl font-semibold tracking-normal">{formatCurrency(locale, asset.price)}</div>
                  <div className="mt-2 text-xs text-text-pg-muted">{asset.is_mock ? t(locale, "dashboard.assetMonitor.fallback") : (asset.source_display || (asset.source ? `${asset.source.toUpperCase()}${asset.source_symbol ? ` / ${asset.source_symbol}` : ""}` : "MOCK"))}</div>
                </div>
                <RiskBadge locale={locale} score={asset.risk_score || 50} />
              </div>
              <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border-pg pt-4 text-sm">
                <span className="text-text-pg-muted">{copy.assetMonitor.change24h}</span>
                <span className={asset.change_24h !== undefined && asset.change_24h !== null && asset.change_24h >= 0 ? "text-status-positive" : "text-status-negative"}>{asset.change_24h !== undefined && asset.change_24h !== null ? `${asset.change_24h.toFixed(2)}%` : "-"}</span>
                <span className="text-text-pg-muted">{copy.assetMonitor.volume24h}</span>
                <span>{formatCurrency(locale, asset.volume_24h || 0, true)}</span>
                <span className="text-text-pg-muted">{copy.assetMonitor.openInterest}</span>
                <span>{asset.open_interest != null ? formatCurrency(locale, asset.open_interest, true) : "N/A"}</span>
                <span className="text-text-pg-muted">{copy.assetMonitor.sentiment}</span>
                <span>{Math.round(asset.sentiment_score * 100)}</span>
              </div>
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border-pg pt-3 text-xs text-text-pg-dim">
                <span>{copy.assetMonitor.updated}</span>
                <span>{asset.timestamp ? formatDateTime(locale, asset.timestamp) : "-"}</span>
              </div>
            </ResearchCard>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <ResearchCard className="min-w-0">
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.sections.topSignals}</h2><Badge tone="cyan">{t(locale, "common.badges.signalFusion")}</Badge></div>
          <SignalTable locale={locale} rows={signalRows} />
        </ResearchCard>
        <ResearchCard className="flex min-h-[430px] min-w-0 flex-col">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-border-pg pb-4">
            <div>
              <h2 className="mt-2 text-lg font-semibold">{copy.sections.confidenceDistribution}</h2>
            </div>
            <Badge tone="emerald">{t(locale, "common.badges.liveBoard")}</Badge>
          </div>
          <div className="flex-1 space-y-5">
            {confidenceRows.map((signal) => (
              <div key={signal.id} className="border-b border-border-pg pb-5 last:border-0 last:pb-0">
                <div className="grid grid-cols-[3.5rem_1fr_4.75rem] items-center gap-3">
                  <div className="text-sm font-semibold">{signal.asset}</div>
                  <div className="h-3 bg-bg-panel-muted">
                    <div className="h-full bg-pg-white" style={{ width: `${signal.confidencePct}%` }} />
                  </div>
                  <div className="text-right text-sm tabular-nums">{signal.confidencePct}%</div>
                </div>
                <div className="mt-3 grid grid-cols-[3.5rem_1fr_auto] items-center gap-3 text-xs text-text-pg-muted">
                  <span>{t(locale, "common.risk.label")} {signal.risk_score}</span>
                  <span className="truncate">{signal.signal_type}</span>
                  <span>{signal.direction}</span>
                </div>
              </div>
            ))}
            <div className="grid grid-cols-[3.5rem_1fr_4.75rem] items-center gap-3 border-t border-border-pg pt-4 text-[0.68rem] text-text-pg-dim">
              <span />
              <div className="grid grid-cols-5">
                {[0, 25, 50, 75, 100].map((tick) => <span key={tick} className={tick === 100 ? "text-right" : ""}>{tick}</span>)}
              </div>
              <span />
            </div>
          </div>
        </ResearchCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_0.8fr]">
        <ResearchCard>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.sections.latestDailyBrief}</h2><ActionLink href={withLocale(locale, "/reports")}>{t(locale, "common.actions.openFullReport")}</ActionLink></div>
          <Markdown content={latest.content_markdown} />
        </ResearchCard>
        <div className="space-y-4">
          <ResearchCard>
            <h2 className="mb-3 font-semibold">{copy.sections.dataPipelineHealth}</h2>
            <div className="grid gap-2">{dataSources.sources.slice(0, 7).map((source) => <div key={source.source} className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-3 text-sm"><span>{source.source}</span><DataSourceStatusBadge locale={locale} status={source.status} /></div>)}</div>
          </ResearchCard>
          <DiligenceLedger locale={locale} items={copy.diligence} />
        </div>
      </div>
    </div>
  );
}
