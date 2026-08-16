"use client";

import { useEffect, useRef, useState } from "react";

export type ConnectCopy = {
  eyebrow: string;
  title: string;
  subtitle: string;
  columns: { users: string; execution: string; bus: string; outputs: string };
  nodes: Record<string, { title: string; sub: string }>;
  legend: { flow: string; live: string; active: string };
};

type NodeId = "node1" | "node2" | "execution" | "risk" | "nexus" | "venue" | "metrics" | "logs";
type ColumnId = "users" | "execution" | "bus" | "outputs";

const COLUMNS: { id: ColumnId; nodes: NodeId[] }[] = [
  { id: "users", nodes: ["node1", "node2"] },
  { id: "execution", nodes: ["execution", "risk"] },
  { id: "bus", nodes: ["nexus"] },
  { id: "outputs", nodes: ["venue", "metrics", "logs"] },
];

const CONNECTIONS: [NodeId, NodeId][] = [
  ["node1", "execution"],
  ["node2", "execution"],
  ["node1", "risk"],
  ["node2", "risk"],
  ["execution", "nexus"],
  ["risk", "nexus"],
  ["nexus", "venue"],
  ["nexus", "metrics"],
  ["nexus", "logs"],
];

const LIVE_NODES: NodeId[] = ["node1", "node2"];
const ACTIVE_NODES: NodeId[] = ["execution", "risk", "nexus"];

export function HowItConnects({ copy }: { copy: ConnectCopy }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Partial<Record<NodeId, HTMLDivElement | null>>>({});
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [paths, setPaths] = useState<string[]>([]);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const measure = () => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      if (rect.width < 420) {
        setSize({ width: 0, height: 0 });
        setPaths([]);
        return;
      }
      const anchor = (id: NodeId, side: "left" | "right") => {
        const el = nodeRefs.current[id];
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          x: (side === "right" ? r.right : r.left) - rect.left,
          y: r.top + r.height / 2 - rect.top,
        };
      };
      const next = CONNECTIONS.map(([from, to]) => {
        const a = anchor(from, "right");
        const b = anchor(to, "left");
        if (!a || !b) return null;
        const dx = Math.max(24, (b.x - a.x) / 2);
        return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
      }).filter((value): value is string => value !== null);
      setPaths(next);
      setSize({ width: rect.width, height: rect.height });
    };

    measure();
    const observer = new ResizeObserver(measure);
    if (containerRef.current) {
      observer.observe(containerRef.current);
    }
    window.addEventListener("resize", measure);

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(media.matches);
    const onMediaChange = (event: MediaQueryListEvent) => setReducedMotion(event.matches);
    media.addEventListener("change", onMediaChange);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      media.removeEventListener("change", onMediaChange);
    };
  }, []);

  return (
    <div>
      <style>{`
        .pg-conn-path { stroke-dasharray: 3 8; animation: pg-conn-flow 1.4s linear infinite; }
        @keyframes pg-conn-flow { to { stroke-dashoffset: -22; } }
        @media (prefers-reduced-motion: reduce) {
          .pg-conn-path { animation: none; }
        }
      `}</style>

      <div ref={containerRef} className="relative overflow-hidden border border-border-pg bg-grid-pattern bg-grid">
        <div className="relative z-10 grid grid-cols-2 gap-2 p-3 md:grid-cols-4 md:gap-2.5 md:p-4">
          {COLUMNS.map((column) => (
            <div key={column.id} className="flex flex-col gap-2">
              <div className="border-b border-border-pg pb-1.5 text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-text-pg-muted">
                {copy.columns[column.id]}
              </div>
              {column.nodes.map((id) => (
                <div
                  key={id}
                  ref={(el) => {
                    nodeRefs.current[id] = el;
                  }}
                  className={`border px-2.5 py-2 ${id === "nexus" ? "border-border-pg-strong bg-pg-panel-2" : "border-border-pg bg-bg-panel"}`}
                >
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="text-[0.7rem] font-semibold leading-tight text-text-pg">{copy.nodes[id].title}</span>
                    {LIVE_NODES.includes(id) ? (
                      <span className="h-1.5 w-1.5 shrink-0 animate-pulse-slow rounded-full bg-status-positive" />
                    ) : ACTIVE_NODES.includes(id) ? (
                      <span className="shrink-0 text-[0.55rem] uppercase tracking-[0.1em] text-status-positive">{copy.legend.active}</span>
                    ) : null}
                  </div>
                  <div className="mt-1 font-mono text-[0.6rem] leading-tight text-text-pg-muted">{copy.nodes[id].sub}</div>
                </div>
              ))}
            </div>
          ))}
        </div>

        {size.width > 0 ? (
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-0 h-full w-full"
            width={size.width}
            height={size.height}
          >
            {paths.map((path, index) => (
              <g key={index}>
                <path d={path} fill="none" stroke="rgba(255,255,255,0.16)" strokeWidth="1" className="pg-conn-path" />
                {!reducedMotion ? (
                  <>
                    <circle r="2" fill="var(--info)">
                      <animateMotion dur={`${2.8 + (index % 3) * 0.5}s`} repeatCount="indefinite" path={path} />
                    </circle>
                    <circle r="2" fill="var(--positive)">
                      <animateMotion dur={`${2.8 + (index % 3) * 0.5}s`} begin={`${1.4 + (index % 3) * 0.25}s`} repeatCount="indefinite" path={path} />
                    </circle>
                  </>
                ) : null}
              </g>
            ))}
          </svg>
        ) : null}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[0.6rem] text-text-pg-dim">
        <span className="flex items-center gap-1.5">
          <svg width="36" height="6" viewBox="0 0 36 6" aria-hidden="true">
            <path d="M1 3 H35" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5" strokeDasharray="3 4" className="pg-conn-path" />
          </svg>
          {copy.legend.flow}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 animate-pulse-slow rounded-full bg-status-positive" />
          {copy.legend.live}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-status-positive" />
          {copy.legend.active}
        </span>
      </div>
    </div>
  );
}
