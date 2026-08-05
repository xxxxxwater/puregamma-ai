"use client";

import { useEffect, useMemo, useState } from "react";
import { Markdown } from "@/components/markdown";
import { SendReportButton } from "@/components/actions";
import { DailyBriefControls } from "@/components/daily-brief-controls";
import { Badge, CreditCostBadge, EmptyState, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { type ReportRow } from "@/lib/api";
import { formatDateTime } from "@/lib/formatters";
import { t } from "@/lib/translations";
import type { Locale } from "@/i18n/routing";

const DAILY_REPORT_FRESH_HOURS = 36;

function reportFreshness(report: ReportRow, locale: Locale) {
  const createdAt = new Date(report.created_at).getTime();
  const ageHours = Number.isFinite(createdAt) ? (Date.now() - createdAt) / 36e5 : Number.POSITIVE_INFINITY;
  const stale = ageHours > DAILY_REPORT_FRESH_HOURS;
  const age = ageHours >= 24
    ? locale === "zh" ? `${Math.floor(ageHours / 24)} 天前` : `${Math.floor(ageHours / 24)}d ago`
    : locale === "zh" ? `${Math.max(1, Math.floor(ageHours))} 小时前` : `${Math.max(1, Math.floor(ageHours))}h ago`;
  const label = stale ? (locale === "zh" ? "已过期" : "Stale") : t(locale, "common.badges.available");
  return { stale, age, label };
}

export default function ReportsPage({ locale, reports, copy, filters }: { locale: Locale; reports: ReportRow[]; copy: { eyebrow: string; title: string; subtitle: string; archive: Record<string, string>; detail: Record<string, string> }; filters: string[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    if (typeof window === "undefined") return reports[0]?.id ?? null;
    const param = new URLSearchParams(window.location.search).get("report");
    return param && reports.some((report) => report.id === param) ? param : reports[0]?.id ?? null;
  });
  const selected = useMemo(() => reports.find((report) => report.id === selectedId) ?? reports[0] ?? null, [reports, selectedId]);
  const zh = locale === "zh";

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (selected) params.set("report", selected.id);
    else params.delete("report");
    window.history.replaceState(null, "", `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`);
  }, [selected]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="01"
        actions={<div className="flex flex-wrap gap-2"><DailyBriefControls locale={locale} /><CreditCostBadge locale={locale} cost={10} /></div>}
      />
      <div className="flex flex-wrap gap-2">{filters.map((filter) => <Badge key={filter} tone="neutral">{filter}</Badge>)}</div>
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <ResearchCard>
          <div className="mb-4 border-b border-border-pg pb-3">
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{copy.archive.eyebrow}</div>
            <h2 className="mt-2 font-semibold">{copy.archive.title}</h2>
          </div>
          <div className="space-y-3">
            {reports.map((report, index) => {
              const freshness = reportFreshness(report, locale);
              const isSelected = report.id === selected?.id;
              return (
              <button key={report.id} type="button" onClick={() => setSelectedId(report.id)} className={`grid w-full grid-cols-[42px_1fr] gap-3 border p-3 text-left transition ${isSelected ? "border-border-pg-strong bg-bg-panel" : "border-border-pg bg-bg-panel-muted hover:border-border-pg-strong"}`}>
                <div className="text-sm text-text-pg-dim">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <div className="font-medium">{report.title}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {report.assets.slice(0, 3).map((asset) => <Badge key={asset}>{asset}</Badge>)}
                    <Badge tone="neutral"><StatusDot tone={freshness.stale ? "amber" : "emerald"} /> {freshness.label}</Badge>
                    <Badge tone="neutral">{copy.detail.language}: {(report.language || locale).toUpperCase()}</Badge>
                  </div>
                  <div className="mt-3 grid gap-1 text-xs text-text-pg-muted">
                    <span>{copy.archive.created}: {formatDateTime(locale, report.created_at)}</span>
                    <span>{copy.archive.sourceFreshness}: {report.source_intelligence_id ? `${freshness.label} · ${freshness.age}` : "-"}</span>
                    <span className={isSelected ? "text-text-pg" : "text-text-pg underline-offset-4 hover:underline"}>{copy.archive.openReport}</span>
                  </div>
                </div>
              </button>
              );
            })}
            {!reports.length ? <EmptyState title={copy.archive.emptyTitle} description={copy.archive.emptyDescription} /> : null}
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
                    <Badge tone="neutral"><StatusDot tone={reportFreshness(selected, locale).stale ? "amber" : "emerald"} /> {reportFreshness(selected, locale).label} · {reportFreshness(selected, locale).age}</Badge>
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
