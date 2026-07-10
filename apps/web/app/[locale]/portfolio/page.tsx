import type { Metadata } from "next";
import { ActionLink, AllocationTable, Badge, DiligenceLedger, MetricCard, NAVCurveCard, PageHeader, PortfolioNavCard, PositionsTable, ResearchCard } from "@/components/puregamma";
import { getPortfolioSnapshot } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "portfolio", "/portfolio");
}

export default async function PortfolioPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "portfolio");
  const portfolio = await getPortfolioSnapshot(locale);
  return (
    <div className="space-y-5">
      <PageHeader eyebrow={copy.eyebrow} title={copy.title} description={copy.subtitle} sectionNumber="02" actions={<><ActionLink href={withLocale(locale, "/integrations")}>{copy.actions.syncAll}</ActionLink><ActionLink href={withLocale(locale, "/reports")}>{copy.actions.generateBrief}</ActionLink></>} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <PortfolioNavCard locale={locale} nav={portfolio.nav} pnlUsd={portfolio.dailyPnlUsd} pnlPct={portfolio.dailyPnlPct} partial={portfolio.partialData} />
        <MetricCard label={copy.metrics.cashStablecoin} value={formatCurrency(locale, portfolio.cash, true)} detail={copy.metrics.liquidityBuffer} tone="cyan" />
        <MetricCard label={copy.metrics.cryptoExposure} value={formatPercent(locale, portfolio.cryptoExposure * 100)} detail={copy.metrics.btcBetaIncluded} tone="emerald" />
        <MetricCard label={copy.metrics.equityExposure} value={formatPercent(locale, portfolio.equityExposure * 100)} detail={copy.metrics.mstrProxy} tone="amber" />
        <MetricCard label={copy.metrics.drawdownEstimate} value="-9.8%" detail={copy.metrics.simulatedStress} tone="red" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <NAVCurveCard locale={locale} title={copy.modules.navCurve} data={portfolio.navHistory} />
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.allocation}</h2><AllocationTable locale={locale} rows={portfolio.allocation} /></ResearchCard>
      </div>
      <ResearchCard><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.modules.positions}</h2><Badge tone="amber">{copy.warning}</Badge></div><PositionsTable locale={locale} rows={portfolio.positions} /></ResearchCard>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {copy.riskItems.map((item) => <ResearchCard key={item}><div className="text-sm text-text-pg-muted">{item}</div></ResearchCard>)}
      </div>
      <DiligenceLedger locale={locale} items={copy.diligence} />
    </div>
  );
}
