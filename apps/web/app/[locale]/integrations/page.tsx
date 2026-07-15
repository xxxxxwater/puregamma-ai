import type { Metadata } from "next";
import { Badge, EmptyState, ErrorState, IntegrationConnectorCard, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
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
      {data.unavailable ? <ErrorState title={locale === "zh" ? "连接状态暂不可用" : "Connection status unavailable"} description={locale === "zh" ? "系统不会使用演示连接替代真实状态。" : "Demo connectors will not be substituted for real status."} /> : null}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{data.integrations.map((item) => <IntegrationConnectorCard locale={locale} key={item.name} item={item} />)}</div>
      {!data.unavailable && !data.integrations.length ? <EmptyState title={locale === "zh" ? "尚未连接真实数据源" : "No real integrations connected"} description={locale === "zh" ? "连接只读组合账户后将在此显示状态。" : "Read-only portfolio connections will appear here."} /> : null}
    </div>
  );
}
