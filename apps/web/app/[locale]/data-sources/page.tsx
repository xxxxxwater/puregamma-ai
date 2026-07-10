import type { Metadata } from "next";
import { Badge, PageHeader, ProcessStepper, ResearchCard } from "@/components/puregamma";
import { getDataSources } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";
import { DataSourceTable } from "@/components/data-source-table";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "data-sources", "/data-sources");
}

export default async function DataSourcesPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "data-sources");
  const data = await getDataSources(locale);
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="04"
        actions={<Badge tone="neutral">{copy.batchScan}</Badge>}
      />
      <DataSourceTable initialSources={data.sources} locale={locale} />
      <ResearchCard>
        <h2 className="mb-3 font-semibold">{copy.pipelineFlow}</h2>
        <ProcessStepper steps={copy.flow} />
      </ResearchCard>
    </div>
  );
}
