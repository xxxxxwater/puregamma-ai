"use client";

import { CircleAlert, CircleCheck, CircleSlash, Loader2, ShieldQuestion } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import { humanizeToolName, stepDurationMs, type ToolStep } from "@/lib/agent-run-events";

const STATUS_COPY = {
  en: { running: "Running", awaiting_approval: "Waiting for your approval", completed: "Done", failed: "Failed", denied: "Not run", input: "Input (redacted)", result: "Result", error: "Error", title: "Tool activity", count: (n: number) => `${n} step${n === 1 ? "" : "s"}` },
  zh: { running: "运行中", awaiting_approval: "等待你的批准", completed: "完成", failed: "失败", denied: "未执行", input: "输入（已脱敏）", result: "结果", error: "错误", title: "工具过程", count: (n: number) => `${n} 步` },
};

function StatusIcon({ status }: { status: ToolStep["status"] }) {
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none text-text-pg-muted" aria-hidden />;
  if (status === "awaiting_approval") return <ShieldQuestion className="h-3.5 w-3.5 text-status-warning" aria-hidden />;
  if (status === "completed") return <CircleCheck className="h-3.5 w-3.5 text-text-pg-dim" aria-hidden />;
  if (status === "denied") return <CircleSlash className="h-3.5 w-3.5 text-status-warning" aria-hidden />;
  return <CircleAlert className="h-3.5 w-3.5 text-status-negative" aria-hidden />;
}

function time(iso: string | undefined, locale: Locale) {
  if (!iso) return "";
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/**
 * What the Agent is doing, one quiet row per tool call.
 *
 * Success stays quiet; a failure or denial is the row that stands out. Each
 * row expands to the server-redacted input and the result summary, with the
 * server's own start/end times - never raw secrets or internal traces.
 */
export function ToolTimeline({ steps, locale }: { steps: ToolStep[]; locale: Locale }) {
  if (!steps.length) return null;
  const copy = STATUS_COPY[locale === "zh" ? "zh" : "en"];
  return (
    <section aria-label={copy.title} data-testid="tool-timeline" className="text-xs">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-text-pg-dim">{copy.title} · {copy.count(steps.length)}</p>
      <ol className="space-y-1">
        {steps.map((step) => {
          const duration = stepDurationMs(step);
          const loud = step.status === "failed" || step.status === "denied" || step.status === "awaiting_approval";
          return (
            <li key={step.id} data-status={step.status} className="rounded-lg">
              <details className="group">
                <summary className={`flex min-h-8 cursor-pointer list-none items-center gap-2 rounded-lg px-2 py-1 hover:bg-[var(--pg-surface-hover)] ${loud ? "text-text-pg" : "text-text-pg-muted"}`}>
                  <StatusIcon status={step.status} />
                  <span className="min-w-0 flex-1 truncate">{humanizeToolName(step.tool)}</span>
                  <span className={step.status === "failed" ? "text-status-negative" : step.status === "denied" || step.status === "awaiting_approval" ? "text-status-warning" : "text-text-pg-dim"}>{copy[step.status]}</span>
                  <span className="hidden tabular-nums text-text-pg-dim sm:inline">{time(step.startedAt, locale)}{duration !== null ? ` · ${(duration / 1000).toFixed(duration < 10_000 ? 1 : 0)}s` : ""}</span>
                </summary>
                <div className="ml-6 mt-1 space-y-2 border-l border-border-pg pb-1 pl-3">
                  <p className="font-mono text-[10px] text-text-pg-dim sm:hidden">{time(step.startedAt, locale)}{step.completedAt ? ` → ${time(step.completedAt, locale)}` : ""}</p>
                  {step.arguments && Object.keys(step.arguments).length ? (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-text-pg-dim">{copy.input}</p>
                      <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-[var(--pg-surface-2)] p-2 font-mono text-[11px] leading-4">{JSON.stringify(step.arguments, null, 2)}</pre>
                    </div>
                  ) : null}
                  {step.summary ? <div><p className="text-[10px] uppercase tracking-wide text-text-pg-dim">{copy.result}</p><p className="mt-1 break-words leading-5 text-text-pg-muted">{step.summary}</p></div> : null}
                  {step.error ? <div><p className="text-[10px] uppercase tracking-wide text-text-pg-dim">{copy.error}</p><p className="mt-1 break-words font-mono text-[11px] text-status-negative">{step.error}</p></div> : null}
                </div>
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
