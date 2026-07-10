import type { Metadata } from "next";
import { DrawdownChart, EquityCurveChart } from "@/components/charts";
import { BacktestResultCard, Badge, CreditCostBadge, PageHeader, ProcessStepper, ResearchCard, StatusDot } from "@/components/puregamma";
import { getNautilusStrategies } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "nautilus", "/nautilus");
}

export default async function NautilusPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "nautilus");
  const data = await getNautilusStrategies(locale);
  const drawdown = data.equityCurve.map((point, index) => ({ date: point.date, drawdown: -Math.abs(index % 3) * 2.4 }));
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="05"
        actions={<CreditCostBadge locale={locale} cost={25} />}
      />
      <ResearchCard className="border-border-pg-strong bg-bg-panel-muted">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{copy.modules.liveTradingGuard}</div>
            <p className="mt-2 text-lg font-semibold">{copy.warningTitle}</p>
            <p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.warningBody}</p>
          </div>
          <Badge tone="neutral"><StatusDot tone="amber" /> {t(locale, "common.badges.executionDisabled")}</Badge>
        </div>
      </ResearchCard>
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.strategyCatalog}</h2><div className="space-y-2">{data.strategies.map((strategy, index) => <div key={strategy} className="grid grid-cols-[36px_1fr] border border-border-pg bg-bg-panel-muted p-3 text-sm"><span className="text-text-pg-dim">{String(index + 1).padStart(2, "0")}</span><span>{strategy}</span></div>)}</div></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.runBacktest}</h2><div className="grid gap-3 md:grid-cols-3"><input aria-label={copy.inputs.strategy} className="border border-border-pg bg-bg-panel-muted px-3 py-2" placeholder="BTC Momentum" /><input aria-label={copy.inputs.startDate} className="border border-border-pg bg-bg-panel-muted px-3 py-2" placeholder="2026-01-01" /><input aria-label={copy.inputs.initialCapital} className="border border-border-pg bg-bg-panel-muted px-3 py-2" placeholder="$100,000" /></div><button className="mt-4 border border-border-pg-strong bg-pg-white px-4 py-2 text-sm font-semibold text-pg-black hover:bg-pg-white-soft">{t(locale, "common.actions.runMockBacktest")}</button></ResearchCard>
      </div>
      <BacktestResultCard locale={locale} metrics={data.metrics} />
      <div className="grid gap-4 xl:grid-cols-2"><ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.equityCurve}</h2><EquityCurveChart data={data.equityCurve} /></ResearchCard><ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.drawdown}</h2><DrawdownChart data={drawdown} /></ResearchCard></div>
      <ResearchCard>
        <h2 className="mb-3 font-semibold">{copy.modules.riskAssumptions}</h2>
        <ProcessStepper steps={copy.riskSteps} />
        <p className="mt-3 text-xs text-text-pg-dim">{t(locale, "compliance.backtest")}</p>
      </ResearchCard>
      <ResearchCard><div className="grid gap-3 md:grid-cols-4"><Badge tone="neutral"><StatusDot tone="amber" /> {t(locale, "common.badges.paperStopped")}</Badge><Badge tone="neutral">{copy.latestEquity}</Badge><Badge tone="neutral"><StatusDot tone="red" /> {copy.drawdownBadge}</Badge><Badge tone="neutral">NAUTILUS_LIVE_TRADING_ENABLED=false</Badge><Badge tone="neutral">NAUTILUS_ALLOW_LIVE_ORDER=false</Badge></div></ResearchCard>
    </div>
  );
}
