import type { Metadata } from "next";
import { GeneratePlaybookButton } from "@/components/actions";
import { Badge, CreditCostBadge, PageHeader, ResearchCard, StrategyCard } from "@/components/puregamma";
import { getNautilusStrategies, fallbackPlaybooksForLocale } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "playbooks", "/playbooks");
}

export default async function PlaybooksPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "playbooks");
  await getNautilusStrategies(locale);
  const playbooks = fallbackPlaybooksForLocale(locale);
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="04"
        actions={<><CreditCostBadge locale={locale} cost={30} /><GeneratePlaybookButton /></>}
      />
      <ResearchCard>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-text-pg-muted">{copy.notice}</p>
          <Badge tone="neutral">{t(locale, "compliance.notFinancialAdvice")}</Badge>
        </div>
      </ResearchCard>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {playbooks.playbooks.map((item) => <StrategyCard locale={locale} key={item.strategy_name} item={item} />)}
      </div>
    </div>
  );
}
