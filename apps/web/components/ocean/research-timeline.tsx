"use client";

import { CircleCheck, CircleX, CircleDashed, Loader2 } from "lucide-react";

export type TimelineStatus = "done" | "active" | "pending" | "failed" | "skipped";

export type TimelineNode = {
  id: string;
  en: string;
  zh: string;
  status: TimelineStatus;
  detail?: string;
};

/** Canonical Harness research stage order (frozen contract). */
export const RESEARCH_STAGES: { id: string; en: string; zh: string }[] = [
  { id: "question", en: "User Question", zh: "用户问题" },
  { id: "planner", en: "Agent Planner", zh: "Agent 规划" },
  { id: "sources", en: "Data Sources", zh: "数据源" },
  { id: "evidence", en: "Evidence Collection", zh: "证据收集" },
  { id: "validation", en: "Validation", zh: "验证" },
  { id: "artifact", en: "Research Artifact", zh: "研究产出" },
];

/** Maps a backend run status to per-stage states. Unknown status -> all pending. */
export function stagesForStatus(status: string): TimelineNode[] {
  const order = ["question", "planner", "sources", "evidence", "validation", "artifact"];
  let activeIndex: number;
  switch (status) {
    case "queued": activeIndex = 0; break;
    case "preparing": activeIndex = 1; break;
    case "running": activeIndex = 2; break;
    case "validating": activeIndex = 4; break;
    case "completed": activeIndex = 6; break;
    case "degraded": activeIndex = 6; break;
    case "failed":
    case "timed_out":
      return RESEARCH_STAGES.map((stage, index) => ({
        ...stage,
        status: index < 4 ? "done" : (index === 4 || index === 5) && status === "failed" ? "failed" : "pending",
      })) as TimelineNode[];
    case "canceled":
      return RESEARCH_STAGES.map((stage, index) => ({ ...stage, status: index < 2 ? "done" : "skipped" })) as TimelineNode[];
    default:
      activeIndex = -1;
  }
  return RESEARCH_STAGES.map((stage, index): TimelineNode => ({
    ...stage,
    status: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending",
  }));
}

const STATUS_ICON: Record<TimelineStatus, typeof CircleCheck> = {
  done: CircleCheck,
  active: Loader2,
  pending: CircleDashed,
  failed: CircleX,
  skipped: CircleX,
};

/**
 * Research task timeline: Question -> Planner -> Sources -> Evidence ->
 * Validation -> Artifact. Text labels always present; never color-only.
 */
export function ResearchTimeline({ nodes, locale }: { nodes: TimelineNode[]; locale: "en" | "zh" }) {
  return (
    <ol className="space-y-0" aria-label={locale === "zh" ? "研究任务时间线" : "Research timeline"}>
      {nodes.map((node, index) => {
        const Icon = STATUS_ICON[node.status];
        const isLast = index === nodes.length - 1;
        const textClass =
          node.status === "failed"
            ? "text-status-negative"
            : node.status === "active"
              ? "font-medium text-ocean-cyan"
              : node.status === "done"
                ? "text-text-pg"
                : "text-text-pg-dim";
        return (
          <li key={node.id} className="relative flex gap-3 pb-4 last:pb-0">
            {!isLast ? <span aria-hidden className="absolute left-[11px] top-6 h-full w-px bg-border-pg" /> : null}
            <span className={`relative z-10 mt-0.5 grid h-6 w-6 shrink-0 place-items-center border ${node.status === "active" ? "ocean-stage-active border-ocean-line text-ocean-cyan" : node.status === "failed" ? "border-status-negative text-status-negative" : "border-border-pg text-text-pg-muted"}`}>
              <Icon className={`h-3.5 w-3.5 ${node.status === "active" ? "animate-spin" : ""}`} aria-hidden />
            </span>
            <div className="ocean-fade-in min-w-0" style={{ animationDelay: `${index * 60}ms` }}>
              <div className={`flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm ${textClass}`}>
                <span className="font-medium">{locale === "zh" ? node.zh : node.en}</span>
                {node.status === "failed" ? <span className="text-xs">{locale === "zh" ? "失败" : "failed"}</span> : null}
                {node.status === "skipped" ? <span className="text-xs">{locale === "zh" ? "已跳过" : "skipped"}</span> : null}
              </div>
              {node.detail ? <p className="mt-0.5 text-xs leading-5 text-text-pg-muted">{node.detail}</p> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
