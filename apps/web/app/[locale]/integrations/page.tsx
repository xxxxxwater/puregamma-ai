import type { Metadata } from "next";
import { Badge, IntegrationConnectorCard, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { getIntegrations } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "integrations", "/integrations");
}

export default async function IntegrationsPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "integrations");
  const data = await getIntegrations(locale);
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="03"
      />
      <ResearchCard className="border-border-pg-strong bg-bg-panel-muted">
        <Badge tone="neutral"><StatusDot tone="amber" /> {copy.securityNotice}</Badge>
        <p className="mt-3 text-sm leading-6 text-text-pg-muted">{copy.securityCopy}</p>
      </ResearchCard>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{data.integrations.map((item) => <IntegrationConnectorCard locale={locale} key={item.name} item={item} />)}</div>
    </div>
  );
}
