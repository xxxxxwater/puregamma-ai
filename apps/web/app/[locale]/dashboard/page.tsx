import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { GlobalMarketTerminal } from "@/components/global-market-terminal";
import { HyperliquidMarketPanel } from "@/components/hyperliquid-market-panel";
import { Markdown } from "@/components/markdown";
import { TodayActivity } from "@/components/today-activity";
import { EmptyState, ErrorState } from "@/components/puregamma";
import { SectionLabel, TerminalPanel } from "@/components/terminal/editorial";
import { IntelligenceHero } from "@/components/terminal/intelligence-hero";

import { PortfolioNav } from "@/components/terminal/portfolio-nav";
import type { MarketStatus } from "@/lib/chrono";
import { ChronoEntrance } from "@/components/chrono/chrono-entrance";
import { ChronoSlices } from "@/components/chrono/chrono-slices";
import { getDashboard, type ReportRow } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

function fmtDate(value: string, locale: Locale) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" });
}

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "dashboard", "/dashboard");
}

export default async function DashboardPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const zh = locale === "zh";
  const copy = getMessageNamespace(locale, "dashboard");
  const { market, subscription, reports } = await getDashboard(locale);

  const status: MarketStatus = (market as { unavailable?: boolean }).unavailable ? "waiting" : (market.mockMode ? "stale" : "live");
  const liveAssets = typeof market.live_assets === "number" ? market.live_assets : null;
  const recentReports: ReportRow[] = Array.isArray(reports.reports) ? reports.reports.slice(0, 4) : [];
  const latest = reports.reports[0];
  const dataAsOf = market.assets.reduce<string | null>((latestTimestamp, asset) => {
    if (!asset.timestamp || Number.isNaN(new Date(asset.timestamp).getTime())) return latestTimestamp;
    if (!latestTimestamp || new Date(asset.timestamp).getTime() > new Date(latestTimestamp).getTime()) return asset.timestamp;
    return latestTimestamp;
  }, null);
  const liveLabel = status === "live" && liveAssets !== null && liveAssets > 0 ? (zh ? `${liveAssets} 个实时资产` : `${liveAssets} live assets`) : null;

  return (
    <ChronoSlices className="dashboard-briefing">
      <ChronoEntrance>
        <IntelligenceHero
          locale={locale}
          eyebrow={copy.heroEyebrow}
          title={copy.heroTitle}
          byline={copy.heroByline}
          status={status}
          dataAsOf={dataAsOf}
          liveLabel={liveLabel}
        />
      </ChronoEntrance>

      {subscription.unavailable ? <div className="chrono-slice" data-chrono-slice><ErrorState title={copy.accountBillingUnavailable} description={copy.accountBillingUnavailableDesc} /></div> : null}

      <div className="hub-grid">
        <div className="hub-col">
          <div className="section-row"><SectionLabel>{copy.sectionThesis}</SectionLabel><span className="text-[0.72rem] text-muted-2">{copy.sectionThesisDetail}</span></div>
          <div className="chrono-slice" data-chrono-slice>
            <TerminalPanel>
              {latest ? <Markdown content={latest.content_markdown} /> : <EmptyState title={copy.noBrief} description={copy.noBriefDesc} />}
            </TerminalPanel>
          </div>
          <div className="section-row"><SectionLabel>{copy.sectionTrail}</SectionLabel><span className="text-[0.72rem] text-muted-2">{copy.sectionTrailDetail}</span></div>
          <div className="chrono-slice" data-chrono-slice>
            <TerminalPanel>
              {recentReports.length === 0 ? <p className="text-sm text-muted">{copy.evidenceEmpty}</p> :
                <ul className="divide-y divide-border">
                  {recentReports.map((report) => (<li key={report.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-text-pg">{report.title}</div>
                      <div className="mt-0.5 text-[0.7rem] text-muted-2">{report.report_type}</div>
                    </div>
                    <span className="shrink-0 text-[0.7rem] tabular-nums text-muted-2">{fmtDate(report.created_at, locale)}</span>
                  </li>))}
                </ul>}
            </TerminalPanel>
          </div>
        </div>

        <div className="hub-col">
          <PortfolioNav locale={locale} />
          <div className="section-row"><SectionLabel>{copy.sectionPulse}</SectionLabel><span className="text-[0.72rem] text-muted-2">{copy.sectionPulseDetail}</span></div>
          <div className="chrono-slice" data-chrono-slice><GlobalMarketTerminal locale={locale} /></div>
        </div>
      </div>

      <section className="chrono-slice" data-chrono-slice aria-label={zh ? "实时市场观察" : "Live market watch"}>
        <div className="section-row"><SectionLabel>{zh ? "实时市场观察" : "Live market watch"}</SectionLabel><span className="text-[0.72rem] text-muted-2">{zh ? "Hyperliquid · 真实行情" : "Hyperliquid · live tape"}</span></div>
        <HyperliquidMarketPanel locale={locale} />
      </section>

      <section className="chrono-slice" data-chrono-slice aria-label={zh ? "今日决策" : "Today decisions"}>
        <div className="section-row"><SectionLabel>{copy.sectionToday}</SectionLabel><span className="text-[0.72rem] text-muted-2">{copy.sectionTodayDetail}</span></div>
        <TodayActivity locale={locale} />
      </section>

      <div className="chrono-slice" data-chrono-slice>
        <Link href={withLocale(locale, "/onboarding/assets")} className="terminal-panel flex items-center justify-between gap-4 transition hover:border-foreground/30">
          <div>
            <div className="text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-muted">{zh ? "首次设置" : "First-time setup"}</div>
            <div className="mt-1 text-sm font-medium">{zh ? "连接数据源、配置通知与阅读偏好" : "Connect data sources, notifications, and reading preferences"}</div>
          </div>
          <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-2" aria-hidden />
        </Link>
      </div>
    </ChronoSlices>
  );
}
