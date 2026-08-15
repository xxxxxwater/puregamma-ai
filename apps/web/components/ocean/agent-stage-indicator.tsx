"use client";

import { Check } from "lucide-react";

export type AgentStage = "understanding" | "selecting" | "collecting" | "validating" | "preparing";

const STAGES: { id: AgentStage; en: string; zh: string }[] = [
  { id: "understanding", en: "Understanding request", zh: "理解问题" },
  { id: "selecting", en: "Selecting tools", zh: "选择工具" },
  { id: "collecting", en: "Collecting evidence", zh: "收集证据" },
  { id: "validating", en: "Validating result", zh: "验证结果" },
  { id: "preparing", en: "Preparing answer", zh: "生成回答" },
];

const ORDER: Record<AgentStage, number> = {
  understanding: 0,
  selecting: 1,
  collecting: 2,
  validating: 3,
  preparing: 4,
};

/**
 * Visible working-phase status for the Agent.
 * Surfaces WHAT the agent is doing, never chain-of-thought or tool internals.
 */
export function AgentStageIndicator({ stage, locale, detail }: { stage: AgentStage | null; locale: "en" | "zh"; detail?: string }) {
  const zh = locale === "zh";
  if (!stage) return null;
  const activeIndex = ORDER[stage];
  return (
    <div role="status" aria-live="polite" className="border border-border-pg bg-bg-app px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px]">
        <span className="font-medium text-text-pg">{zh ? "Agent 正在工作" : "Agent is working"}</span>
        {STAGES.map((item, index) => {
          const done = index < activeIndex;
          const active = index === activeIndex;
          return (
            <span key={item.id} className={`inline-flex items-center gap-1 ${active ? "ocean-stage-active font-medium text-ocean-cyan" : done ? "text-text-pg-muted" : "text-text-pg-dim"}`}>
              {done ? <Check className="h-3 w-3" aria-hidden /> : <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-ocean-cyan" : "bg-text-pg-dim"}`} aria-hidden />}
              {zh ? item.zh : item.en}
            </span>
          );
        })}
        {detail ? <span className="text-text-pg-dim">· {detail}</span> : null}
      </div>
    </div>
  );
}

/** Stage progression derived from SSE events. See components/agent-chat.tsx. */
export function nextAgentStage(current: AgentStage | null, stage: AgentStage): AgentStage {
  if (!current) return stage;
  return ORDER[stage] > ORDER[current] ? stage : current;
}
