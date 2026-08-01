import type { Metadata } from "next";
import { BookOpen, CreditCard, Database } from "lucide-react";
import { HyperliquidMarketPanel } from "@/components/hyperliquid-market-panel";
import { getDashboard } from "@/lib/api";
import { ActionLink, Badge, EmptyState, ErrorState, MetricCard, PageHeader, ResearchCard, RiskBadge } from "@/components/puregamma";
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
  const { market, subscription, reports } = await getDashboard(locale);
  const latest = reports.reports[0];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="00"
        actions={<ActionLink href={withLocale(locale, "/reports")}>{t(locale, "common.actions.openResearchLibrary")}</ActionLink>}
      />

      {subscription.unavailable ? <ErrorState title={copy.accountBillingUnavailable} description={copy.accountBillingUnavailableDesc} /> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard label={copy.metrics.creditBalance} value={subscription.unavailable ? "--" : String(subscription.credit_balance)} detail={subscription.unavailable ? copy.dataUnavailable : `${subscription.plan} plan`} tone="cyan" icon={<CreditCard className="h-4 w-4" />} />
        <MetricCard label={copy.researchBriefs} value={String(reports.reports.length)} detail={copy.researchBriefsDetail} tone="emerald" icon={<BookOpen className="h-4 w-4" />} />
        <MetricCard label={copy.liveAssets} value={String(market.live_assets || 0)} detail={(market.source_summary || []).join(" / ") || copy.sourcesUnavailable} tone="amber" icon={<Database className="h-4 w-4" />} />
      </div>

      <HyperliquidMarketPanel locale={locale} />

      <section>
        <div className="mb-3 text-eyebrow uppercase text-text-pg-muted">{copy.assetMonitor.title}</div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {market.assets.map((asset) => (
            <ResearchCard key={asset.symbol} className="flex min-h-[238px] flex-col">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-xl font-semibold">{asset.symbol}</div>
                    <Badge tone={asset.is_realtime ? "emerald" : "amber"}>{asset.is_realtime ? copy.assetMonitor.liveRest : copy.delayedQuote}</Badge>
                  </div>
                  <div className="mt-3 text-3xl font-semibold tracking-normal">{formatCurrency(locale, asset.price)}</div>
                  <div className="mt-2 text-xs text-text-pg-muted">{asset.source_display || (asset.source ? `${asset.source.toUpperCase()}${asset.source_symbol ? ` / ${asset.source_symbol}` : ""}` : "-")}</div>
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
                <span className="text-text-pg-muted">{copy.fundingRate}</span>
                <span>{asset.funding_rate != null ? `${(asset.funding_rate * 100).toFixed(3)}%` : "N/A"}</span>
              </div>
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border-pg pt-3 text-xs text-text-pg-dim">
                <span>{copy.assetMonitor.updated}</span>
                <span>{asset.timestamp ? formatDateTime(locale, asset.timestamp) : "-"}</span>
              </div>
            </ResearchCard>
          ))}
          {!market.assets.length ? <EmptyState title={copy.marketUnavailable} description={copy.marketUnavailableDesc} /> : null}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1fr_0.8fr]">
        <ResearchCard>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.sections.latestDailyBrief}</h2><ActionLink href={withLocale(locale, "/reports")}>{t(locale, "common.actions.openFullReport")}</ActionLink></div>
          {latest ? <Markdown content={latest.content_markdown} /> : <EmptyState title={copy.noBrief} description={copy.noBriefDesc} />}
        </ResearchCard>
        <div className="space-y-4">
          <ResearchCard className="overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-border-pg px-4 py-3">
              <div>
                <div className="text-eyebrow uppercase text-text-pg-muted">{copy.marketTerminal}</div>
                <h2 className="mt-1 font-semibold">{copy.crossMarketTape}</h2>
              </div>
              <span className="font-mono text-[11px] text-status-positive">● FEED</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] font-mono text-xs">
                <thead className="bg-bg-panel-muted text-left text-[10px] uppercase text-text-pg-dim">
                  <tr><th className="px-4 py-2 font-medium">{copy.ticker}</th><th className="px-3 py-2 text-right font-medium">{copy.last}</th><th className="px-3 py-2 text-right font-medium">%</th><th className="px-3 py-2 font-medium">{copy.source}</th><th className="px-4 py-2 text-right font-medium">UTC</th></tr>
                </thead>
                <tbody>
                  {market.assets.map((asset) => <tr key={asset.symbol} className="border-t border-border-pg/70 hover:bg-bg-panel-muted"><td className="px-4 py-3 font-semibold text-text-pg">{asset.symbol}<span className={`ml-2 text-[9px] ${asset.is_realtime ? "text-status-positive" : "text-status-warning"}`}>{asset.is_realtime ? "LIVE" : "DLY"}</span></td><td className="px-3 py-3 text-right text-text-pg">{formatCurrency(locale, asset.price)}</td><td className={`px-3 py-3 text-right ${asset.change_24h != null && asset.change_24h >= 0 ? "text-status-positive" : "text-status-negative"}`}>{asset.change_24h != null ? `${asset.change_24h >= 0 ? "+" : ""}${asset.change_24h.toFixed(2)}` : "-"}</td><td className="max-w-[150px] truncate px-3 py-3 text-text-pg-muted">{asset.source_display || asset.source || "-"}</td><td className="px-4 py-3 text-right text-text-pg-dim">{asset.timestamp ? new Date(asset.timestamp).toISOString().slice(11, 19) : "-"}</td></tr>)}
                </tbody>
              </table>
              {!market.assets.length ? <p className="p-4 text-sm text-text-pg-muted">{copy.waitingFeed}</p> : null}
            </div>
          </ResearchCard>
        </div>
      </div>
    </div>
  );
}
