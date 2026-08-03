import type { Metadata } from "next";
import { GlobalMarketTerminal } from "@/components/global-market-terminal";
import { HyperliquidMarketPanel } from "@/components/hyperliquid-market-panel";
import { Markdown } from "@/components/markdown";
import { ActionLink, EmptyState, ErrorState, PageHeader, ResearchCard } from "@/components/puregamma";
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
          <GlobalMarketTerminal locale={locale} />
        </div>
      </div>
    </div>
  );
}
