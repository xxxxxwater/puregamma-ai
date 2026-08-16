"use client";

import { Database, FileSearch, Lightbulb, ShieldAlert, Quote } from "lucide-react";

export type EvidenceNodeKind = "source" | "evidence" | "conclusion" | "limitation" | "citation";

export type EvidenceNode = {
  id: string;
  kind: EvidenceNodeKind;
  label: string;
  count?: number;
  detail?: string;
  status?: "ok" | "partial" | "missing";
};

const KIND_META: Record<EvidenceNodeKind, { icon: typeof Database; label: { en: string; zh: string }; color: string }> = {
  source: { icon: Database, label: { en: "Data Source", zh: "数据源" }, color: "var(--ocean-blue)" },
  evidence: { icon: FileSearch, label: { en: "Evidence Snapshot", zh: "证据快照" }, color: "var(--ocean-cyan)" },
  conclusion: { icon: Lightbulb, label: { en: "Conclusion", zh: "结论" }, color: "var(--ocean-violet)" },
  limitation: { icon: ShieldAlert, label: { en: "Limitation", zh: "限制条件" }, color: "var(--warning)" },
  citation: { icon: Quote, label: { en: "Citation", zh: "引用/来源" }, color: "var(--muted)" },
};

/**
 * Lightweight evidence relationship graph — static layered nodes and SVG
 * connectors. No graph engine, no physics. First-class text, click to focus.
 */
export function EvidenceGraph({ nodes, locale, onSelect }: {
  nodes: EvidenceNode[];
  locale: "en" | "zh";
  onSelect?: (node: EvidenceNode) => void;
}) {
  if (!nodes.length) return null;
  // Static two-column layout: sources/evidence on the left, conclusions/limitations/citations on the right.
  const left = nodes.filter((node) => node.kind === "source" || node.kind === "evidence");
  const right = nodes.filter((node) => node.kind === "conclusion" || node.kind === "limitation" || node.kind === "citation");
  const rowHeight = 64;
  const gap = 28;
  const leftWidth = 170;
  const svgWidth = leftWidth * 2 + gap;
  const svgHeight = Math.max(left.length, right.length, 1) * rowHeight;

  const pointFor = (index: number, column: 0 | 1) => ({
    x: column === 0 ? leftWidth : leftWidth + gap,
    y: index * rowHeight + rowHeight / 2,
  });

  return (
    <div className="relative overflow-x-auto" aria-label={locale === "zh" ? "证据关系图" : "Evidence relationship graph"}>
      <svg aria-hidden className="absolute left-0 top-0 h-full w-full text-border-pg" viewBox={`0 0 ${svgWidth} ${svgHeight}`} preserveAspectRatio="none">
        {left.map((node, index) =>
          right.map((target) => {
            const from = pointFor(index, 0);
            const to = pointFor(right.indexOf(target), 1);
            return (
              <line
                key={`${node.id}-${target.id}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="currentColor"
                strokeOpacity={0.35}
                strokeWidth={1}
                strokeDasharray="3 4"
              />
            );
          })
        )}
      </svg>
      <div className="relative grid min-w-[360px] grid-cols-2 gap-7">
        <div className="space-y-3">
          {left.map((node, index) => (
            <GraphNode key={node.id} node={node} locale={locale} onClick={onSelect} index={index} />
          ))}
        </div>
        <div className="space-y-3">
          {right.map((node, index) => (
            <GraphNode key={node.id} node={node} locale={locale} onClick={onSelect} index={index} />
          ))}
        </div>
      </div>
    </div>
  );
}

function GraphNode({ node, locale, onClick, index }: { node: EvidenceNode; locale: "en" | "zh"; onClick?: (node: EvidenceNode) => void; index: number }) {
  const meta = KIND_META[node.kind];
  const Icon = meta.icon;
  const label = locale === "zh" ? meta.label.zh : meta.label.en;
  const statusClass = node.status === "missing" ? "opacity-50" : node.status === "partial" ? "opacity-75" : "";
  return (
    <button
      type="button"
      onClick={() => onClick?.(node)}
      className={`ocean-fade-in flex w-full items-center gap-2.5 border border-border-pg bg-bg-panel p-2.5 text-left hover:border-border-pg-strong ${statusClass}`}
      style={{ animationDelay: `${index * 50}ms` }}
      aria-label={`${label}: ${node.label}`}
    >
      <span className="grid h-7 w-7 shrink-0 place-items-center border border-border-pg" style={{ color: meta.color }} aria-hidden>
        <Icon className="h-3.5 w-3.5" />
      </span>
      <span className="min-w-0">
        <span className="block text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</span>
        <span className="block truncate text-xs font-medium text-text-pg">{node.label}</span>
        {node.detail ? <span className="block truncate text-[10px] text-text-pg-muted">{node.detail}</span> : null}
      </span>
      {typeof node.count === "number" ? <span className="ml-auto shrink-0 text-xs tabular-nums text-text-pg-muted">{node.count}</span> : null}
      {node.status === "missing" ? <span className="shrink-0 text-[10px] text-text-pg-dim">{locale === "zh" ? "暂无" : "none"}</span> : null}
    </button>
  );
}
