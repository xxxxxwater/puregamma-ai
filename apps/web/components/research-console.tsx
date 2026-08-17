"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarClock, Database, FileSearch, FlaskConical } from "lucide-react";
import { CapabilityGate, useCapabilityGate } from "@/components/ocean/capability-gate";
import { RippleEffect } from "@/components/ocean/ripple-effect";
import { OceanShell } from "@/components/ocean/ocean-shell";
import { StatusBadge, StatusBadgeWithPulse } from "@/components/ocean/status-badge";
import { createResearchRun, getResearchRuns, type HarnessResearchRun } from "@/lib/api";
import { type Locale, withLocale } from "@/i18n/routing";

const ACTIVE_STATUSES = new Set(["queued", "preparing", "running", "validating"]);
const DATA_SOURCE_OPTIONS = ["market", "news", "options", "earnings"] as const;

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
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [sources, setSources] = useState<string[]>(["market", "news"]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string>("");

  const refresh = () => {
    getResearchRuns()
      .then((payload) => {
        setRuns(payload.runs || []);
        setLastRefresh(new Date().toISOString());
      })
      .catch(() => undefined);
  };

  useEffect(() => {
    if (state.status !== "available") return;
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status]);

  const submit = async () => {
    setSubmitting(true);
    setFormError("");
    try {
      await createResearchRun({ name: name.trim() || prompt.trim().slice(0, 40), prompt: prompt.trim(), data_sources: sources, skill: "harness_deep_research" });
      setName("");
      setPrompt("");
      setShowForm(false);
      refresh();
    } catch (error) {
      const detail = (error as { payload?: { detail?: { message?: string } | string } })?.payload?.detail;
      setFormError(typeof detail === "string" ? detail : typeof detail === "object" && detail ? detail.message || "创建失败" : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleSource = (source: string) => {
    setSources((prev) => (prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]));
  };

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
          <div className="mb-4 flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setShowForm((value) => !value)}
              className="border border-border-pg px-3 py-2 text-xs font-medium transition hover:border-border-pg-strong"
            >
              {showForm ? (zh ? "收起" : "Collapse") : (zh ? "+ 新建研究任务" : "+ New research run")}
            </button>
            <p className="text-xs text-text-pg-dim">
              {zh ? "每天最多 3 个任务 · 结果仅供研究参考" : "Up to 3 runs per day · research output only"}
            </p>
          </div>

          {showForm ? (
            <div className="mb-4 border border-border-pg bg-bg-panel p-4">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={zh ? "任务名称(可选)" : "Run name (optional)"}
                className="w-full border border-border-pg bg-transparent px-3 py-2 text-sm text-text-pg outline-none placeholder:text-text-pg-dim focus:border-border-pg-strong"
              />
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={zh ? "研究问题,例如:近 90 天 BTC 资金费率与价格偏离的关系" : "Research question, e.g. how funding rates diverged from BTC price over 90 days"}
                rows={3}
                className="mt-2 w-full border border-border-pg bg-transparent px-3 py-2 text-sm text-text-pg outline-none placeholder:text-text-pg-dim focus:border-border-pg-strong"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {DATA_SOURCE_OPTIONS.map((source) => (
                  <button
                    key={source}
                    type="button"
                    onClick={() => toggleSource(source)}
                    className={`border px-2.5 py-1 text-xs transition ${sources.includes(source) ? "border-ocean-cyan text-ocean-cyan" : "border-border-pg text-text-pg-muted hover:border-border-pg-strong"}`}
                  >
                    {source}
                  </button>
                ))}
              </div>
              {formError ? <p className="mt-2 text-xs text-status-negative">{formError}</p> : null}
              <button
                type="button"
                onClick={() => void submit()}
                disabled={submitting || !prompt.trim()}
                className="mt-3 border border-ocean-cyan px-4 py-2 text-xs font-medium text-ocean-cyan transition disabled:opacity-40"
              >
                {submitting ? (zh ? "创建中…" : "Creating…") : (zh ? "开始研究" : "Start research")}
              </button>
            </div>
          ) : null}

          {runs.length === 0 ? (
            <div className="border border-border-pg bg-bg-panel p-6 text-sm text-text-pg-muted">
              {zh ? "还没有研究任务。点击上方“新建研究任务”开始第一个深度研究。" : "No research runs yet. Click “New research run” above to start your first deep research."}
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
