import type { Metadata } from "next";
import { Markdown } from "@/components/markdown";
import { SendReportButton } from "@/components/actions";
import { Badge, CreditCostBadge, EmptyState, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { getReports } from "@/lib/api";
import { formatDateTime } from "@/lib/formatters";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "reports", "/reports");
}

export default async function ReportsPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "reports");
  const data = await getReports(locale);
  const selected = data.reports[0];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="01"
        actions={<CreditCostBadge locale={locale} cost={10} />}
      />
      <div className="flex flex-wrap gap-2">{copy.filters.map((filter) => <Badge key={filter} tone="neutral">{filter}</Badge>)}</div>
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <ResearchCard>
          <div className="mb-4 border-b border-border-pg pb-3">
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{copy.archive.eyebrow}</div>
            <h2 className="mt-2 font-semibold">{copy.archive.title}</h2>
          </div>
          <div className="space-y-3">
            {data.reports.map((report, index) => (
              <div key={report.id} className="grid grid-cols-[42px_1fr] gap-3 border border-border-pg bg-bg-panel-muted p-3">
                <div className="text-sm text-text-pg-dim">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <div className="font-medium">{report.title}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {report.assets.slice(0, 3).map((asset) => <Badge key={asset}>{asset}</Badge>)}
                    <Badge tone="neutral"><StatusDot tone="emerald" /> {t(locale, "common.badges.available")}</Badge>
                    <Badge tone="neutral">{copy.detail.language}: {(report.language || locale).toUpperCase()}</Badge>
                  </div>
                  <div className="mt-3 grid gap-1 text-xs text-text-pg-muted">
                    <span>{copy.archive.created}: {formatDateTime(locale, report.created_at)}</span>
                    <span>{copy.archive.sourceFreshness}: {report.source_intelligence_id ? t(locale, "common.badges.available") : "-"}</span>
                    <a href="#report-detail" className="text-text-pg underline-offset-4 hover:underline">{copy.archive.openReport}</a>
                  </div>
                </div>
              </div>
            ))}
            {!data.reports.length ? <EmptyState title={copy.archive.emptyTitle} description={copy.archive.emptyDescription} /> : null}
          </div>
        </ResearchCard>
        <ResearchCard className="scroll-mt-24" id="report-detail">
          {selected ? (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border-pg pb-4">
                <div>
                  <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{copy.detail.eyebrow}</div>
                  <h2 className="mt-2 text-xl font-semibold">{selected.title}</h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selected.assets.map((asset) => <Badge key={asset}>{asset}</Badge>)}
                    <Badge tone="neutral">{t(locale, "common.shared.source")}: {selected.source_intelligence_id || "shared-intel"}</Badge>
                    <Badge tone="neutral"><StatusDot tone="emerald" /> {t(locale, "common.badges.available")}</Badge>
                    <Badge tone="neutral">{copy.detail.language}: {(selected.language || locale).toUpperCase()}</Badge>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">{["telegram", "imessage"].map((channel) => <SendReportButton key={channel} channel={channel} reportId={selected.id} />)}</div>
              </div>
              <Markdown content={selected.content_markdown} />
            </>
          ) : (
            <EmptyState title={copy.detail.noSelectionTitle} description={copy.detail.noSelectionDescription} />
          )}
        </ResearchCard>
      </div>
    </div>
  );
}
