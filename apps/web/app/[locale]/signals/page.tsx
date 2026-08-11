import type { Metadata } from "next";
import { ConfidenceDistributionChart } from "@/components/charts";
import { Badge, EmptyState, MetricCard, PageHeader, ResearchCard, RiskBadge, SignalTable, StatusDot } from "@/components/puregamma";
import { getSignals } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "signals", "/signals");
}

export default async function SignalsPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "signals");
  const data = await getSignals(locale);
  const rows = data.signals;
  const bullish = rows.filter((row) => row.direction.includes("long")).length;
  const highRisk = rows.filter((row) => row.risk_score >= 65).length;
  const chart = rows.map((row) => ({ date: row.asset, confidence: Math.round(row.confidence * 100) }));

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="03"
      />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label={copy.metrics.longWatch} value={String(bullish)} detail={copy.metrics.directionalResearchOnly} tone="emerald" />
        <MetricCard label={copy.metrics.shortWatch} value="0" detail={copy.metrics.noActiveShortReview} tone="neutral" />
        <MetricCard label={copy.metrics.monitor} value={String(rows.length - bullish)} detail={copy.metrics.noAllocationAction} tone="info" />
        <MetricCard label={copy.metrics.highConfidence} value={String(rows.filter((row) => row.confidence > 0.65).length)} detail={copy.metrics.confidenceAbove} tone="emerald" />
        <MetricCard label={copy.metrics.highRisk} value={String(highRisk)} detail={copy.metrics.riskAbove} tone="amber" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.4fr_0.6fr]">
        <ResearchCard>{rows.length ? <SignalTable locale={locale} rows={rows} /> : <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />}</ResearchCard>
        <ResearchCard>
          <div className="mb-3 border-b border-border-pg pb-3">
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{copy.confidenceDistribution}</div>
            <h2 className="mt-2 font-semibold">{copy.reviewDensity}</h2>
          </div>
          {rows.length ? <><ConfidenceDistributionChart data={chart} /><div className="mt-4 space-y-2 text-sm">{rows.map((row) => <div key={row.id} className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-2 rounded-lg"><span>{row.asset}</span><RiskBadge locale={locale} score={row.risk_score} /></div>)}</div></> : null}
        </ResearchCard>
      </div>
      <ResearchCard>
        <div className="mb-4 border-b border-border-pg pb-3">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{copy.detail.eyebrow}</div>
          <h2 className="mt-2 font-semibold">{copy.detail.title}</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {rows.map((row, index) => (
            <div key={row.id} className="border border-border-pg bg-bg-panel-muted p-3 text-sm rounded-lg">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-text-pg-dim">{String(index + 1).padStart(2, "0")} / {row.id}</div>
                  <div className="mt-2 font-semibold">{row.asset}</div>
                </div>
                <RiskBadge locale={locale} score={row.risk_score} />
              </div>
              <div className="mt-4 space-y-3 text-text-pg-muted">
                <p><span className="text-text-pg">{copy.detail.thesis}:</span> {row.thesis}</p>
                <p><span className="text-text-pg">{copy.detail.evidence}:</span> {row.catalyst}</p>
                <p><span className="text-text-pg">{copy.detail.risk}:</span> {copy.detail.riskCopy}</p>
                <p><span className="text-text-pg">{copy.detail.invalidation}:</span> {row.invalidation}</p>
                <p><span className="text-text-pg">{copy.detail.dataFreshness}:</span> {copy.detail.freshnessCopy}</p>
              </div>
            </div>
          ))}
        </div>
      </ResearchCard>
    </div>
  );
}
