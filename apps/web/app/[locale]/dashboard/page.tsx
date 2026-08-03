import type { Metadata } from "next";
import { HyperliquidMarketPanel } from "@/components/hyperliquid-market-panel";
import { Markdown } from "@/components/markdown";
import { ActionLink, EmptyState, ErrorState, PageHeader, ResearchCard } from "@/components/puregamma";
import { formatCurrency } from "@/lib/formatters";
import { getDashboard } from "@/lib/api";
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

      <HyperliquidMarketPanel locale={locale} />

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
