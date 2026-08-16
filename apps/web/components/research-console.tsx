"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarClock, Database, FileSearch, FlaskConical } from "lucide-react";
import { CapabilityGate, useCapabilityGate } from "@/components/ocean/capability-gate";
import { RippleEffect } from "@/components/ocean/ripple-effect";
import { OceanShell } from "@/components/ocean/ocean-shell";
import { StatusBadge, StatusBadgeWithPulse } from "@/components/ocean/status-badge";
import { getResearchRuns, type HarnessResearchRun } from "@/lib/api";
import { type Locale, withLocale } from "@/i18n/routing";

const ACTIVE_STATUSES = new Set(["queued", "preparing", "running", "validating"]);

function formatTime(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function ResearchConsole({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const router = useRouter();
  const { state, retry } = useCapabilityGate(() => getResearchRuns(), []);
  const [runs, setRuns] = useState<HarnessResearchRun[]>([]);
  const [lastRefresh, setLastRefresh] = useState<string>("");

  useEffect(() => {
    if (state.status !== "available") return;
    let cancelled = false;
    getResearchRuns()
      .then((payload) => {
        if (cancelled) return;
        setRuns(payload.runs || []);
        setLastRefresh(new Date().toISOString());
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [state.status]);

  return (
    <OceanShell locale={locale} variant="research" className="min-h-[calc(100dvh-7rem)] rounded-2xl">
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
        <header className="mb-6">
          <div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim">
            <FlaskConical className="h-4 w-4" aria-hidden />
            {zh ? "智能研究工作台" : "Intelligence Research Workbench"}
          </div>
          <h1 className="mt-3 text-2xl font-semibold leading-tight md:text-3xl">
            {zh ? "研究任务" : "Research runs"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-pg-muted">
            {zh
              ? "深度研究任务按“问题 → 规划 → 数据源 → 证据 → 验证 → 产出”推进。所有结论附证据与限制条件，仅供研究参考，不构成投资建议。"
              : "Deep research runs follow Question → Planner → Data Sources → Evidence → Validation → Artifact. Every conclusion carries evidence and limitations; research output only, never investment advice."}
          </p>
          {lastRefresh ? (
            <p className="mt-2 text-xs text-text-pg-dim">
              {zh ? "更新于" : "Updated"} {formatTime(lastRefresh, locale)}
            </p>
          ) : null}
        </header>

        <CapabilityGate
          state={state}
          locale={locale}
          title={zh ? "Harness Research 暂不可用" : "Harness Research not available yet"}
          onRetry={retry}
        >
          {runs.length === 0 ? (
            <div className="border border-border-pg bg-bg-panel p-6 text-sm text-text-pg-muted">
              {zh ? "还没有研究任务。Harness Research 开放创建入口后，新任务会显示在这里。" : "No research runs yet. Once the Harness Research creation flow opens, new runs will appear here."}
            </div>
          ) : (
            <ul className="space-y-3">
              {runs.map((run) => (
                <li key={run.id}>
                  <RippleEffect as="div" className="group cursor-pointer">
                    <button
                      type="button"
                      onClick={() => router.push(withLocale(locale, `/research/${run.id}`))}
                      className={`w-full border bg-bg-panel p-4 text-left transition hover:border-border-pg-strong ${ACTIVE_STATUSES.has(run.status) ? "ocean-flowing-border" : "border-border-pg"}`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-text-pg">{run.name || run.id}</div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-pg-dim">
                            <span className="inline-flex items-center gap-1"><CalendarClock className="h-3 w-3" aria-hidden />{zh ? "创建" : "Created"} {formatTime(run.created_at, locale)}</span>
                            <span>{zh ? "更新" : "Updated"} {formatTime(run.updated_at, locale)}</span>
                            <span className="inline-flex items-center gap-1"><Database className="h-3 w-3" aria-hidden />{zh ? "数据源" : "Sources"} {run.data_sources?.length ?? 0}</span>
                            <span className="inline-flex items-center gap-1"><FileSearch className="h-3 w-3" aria-hidden />{zh ? "证据" : "Evidence"} {run.evidence_count ?? 0}</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <StatusBadgeWithPulse domain="research" value={run.status} locale={locale} />
                          <ArrowRight className="h-4 w-4 text-text-pg-dim transition group-hover:translate-x-0.5 group-hover:text-text-pg-muted" aria-hidden />
                        </div>
                      </div>
                      {run.is_degraded || run.status === "failed" || run.status === "timed_out" ? (
                        <p className="mt-2 border-t border-border-pg pt-2 text-xs text-status-warning">
                          {run.is_degraded ? (zh ? "已降级：部分证据缺失，结论仅供参考。" : "Degraded: some evidence is missing; conclusions are partial.") : run.error_message || (zh ? "任务失败。" : "Run failed.")}
                        </p>
                      ) : null}
                      {run.summary ? <p className="mt-2 text-xs leading-5 text-text-pg-muted">{run.summary}</p> : null}
                    </button>
                  </RippleEffect>
                </li>
              ))}
            </ul>
          )}
        </CapabilityGate>
      </div>
    </OceanShell>
  );
}
