"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Terminal, ChevronDown, ChevronUp } from "lucide-react";
import { API_URL } from "@/lib/api";

interface LogEvent {
  t: string;
  ts?: string;
  line?: string;
  bar?: number;
  total?: number;
  pct?: number;
  trades?: number;
  direction?: string;
  price?: number;
  equity?: number;
  position?: number;
  asset?: string;
  message?: string;
}

interface StreamRun {
  id: string;
  status: string;
}

function fmtLite(value: number | undefined, decimals = 2): string {
  if (value === undefined) return "--";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function isTerminal(status: string): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

interface Props {
  run: StreamRun | null;
  localeStr: string;
}

export function BacktestTerminal({ run, localeStr }: Props) {
  const zh = localeStr === "zh";
  const [lines, setLines] = useState<LogEvent[]>([]);
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const streaming = useMemo(
    () => run !== null && !isTerminal(run.status),
    [run]
  );

  // Auto-open when streaming, auto-close idle when terminal + 10s
  useEffect(() => {
    if (streaming) {
      setOpen(true);
    }
  }, [streaming]);

  // Connect / disconnect SSE
  useEffect(() => {
    if (!run || isTerminal(run.status)) {
      // When the run is terminal, close the existing connection after a grace
      // period so the user can read the final output.
      const timer = window.setTimeout(() => {
        eventSourceRef.current?.close();
        eventSourceRef.current = null;
        setConnected(false);
      }, 30_000);
      return () => window.clearTimeout(timer);
    }

    // Don't reconnect if already listening to the same run.
    if (
      eventSourceRef.current &&
      !isTerminal(run.status)
    ) {
      return;
    }

    setLines([]);
    const url = `${API_URL}/backtest-lab/runs/${run.id}/stream`;
    const evt = new EventSource(url, { withCredentials: true });
    evt.addEventListener("message", (msg) => {
      try {
        const parsed: LogEvent = JSON.parse(msg.data);
        setLines((prev) => [...prev, parsed]);
        if (!connected) setConnected(true);
      } catch {
        // Ignore malformed lines.
      }
    });
    evt.addEventListener("open", () => setConnected(true));
    evt.addEventListener("error", () => {
      setConnected(false);
      // EventSource auto-reconnects; if the run is terminal the parent
      // will close us.
    });
    eventSourceRef.current = evt;
    return () => {
      evt.close();
      eventSourceRef.current = null;
    };
  }, [run, connected]);

  // Auto-scroll when new lines appear.
  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [lines]);

  if (!run) {
    return (
      <div className="border border-border-pg bg-bg-panel p-4 text-xs text-text-pg-dim">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4" />
          {zh ? "运行回测后将在此显示终端输出" : "Run a backtest to see terminal output here"}
        </div>
      </div>
    );
  }

  const header = (
    <button
      type="button"
      onClick={() => setOpen((prev) => !prev)}
      className="flex w-full items-center justify-between border border-border-pg bg-bg-panel px-4 py-2.5 text-left text-xs font-semibold"
    >
      <span className="flex items-center gap-2">
        <Terminal className="h-4 w-4" />
        {zh ? "回测终端" : "Backtest Terminal"}
        {streaming ? (
          <span className="inline-flex items-center gap-1 text-status-positive">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-status-positive" />
            {zh ? "运行中" : "Running"}
          </span>
        ) : connected ? (
          <span className="text-text-pg-dim">
            {zh ? "已结束" : "Finished"}
          </span>
        ) : null}
      </span>
      {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
    </button>
  );

  if (!open) return header;

  return (
    <div>
      {header}
      <div
        ref={containerRef}
        className="max-h-96 overflow-y-auto border-x border-b border-border-pg bg-[#0a0a0a] px-4 py-3 font-mono text-[11px] leading-[1.55]"
      >
        {lines.length === 0 ? (
          <span className="text-neutral-600">
            {streaming
              ? `\u2588 ${zh ? "等待工作进程..." : "Waiting for worker..."}`
              : zh
              ? "无输出"
              : "No output"}
          </span>
        ) : (
          lines.map((event, index) => (
            <TerminalLine key={`${index}-${event.t}`} event={event} />
          ))
        )}
        {streaming ? (
          <span className="ml-1 inline-block h-[1.15em] w-[0.55em] animate-pulse bg-neutral-500 align-middle" />
        ) : null}
      </div>
    </div>
  );
}

function TerminalLine({ event }: { event: LogEvent }) {
  const colorClass = useMemo(() => {
    switch (event.t) {
      case "trade":
        return "text-yellow-300";
      case "error":
        return "text-red-400";
      case "warning":
        return "text-amber-300";
      case "metric":
        return "text-cyan-300";
      case "complete":
        return "text-green-300 font-semibold";
      case "start":
        return "text-white";
      case "data":
        return "text-neutral-400";
      case "progress":
        return "text-neutral-300";
      default:
        return "text-neutral-500";
    }
  }, [event.t]);

  const line = event.line;
  if (!line) {
    // Render raw event for trade/progress without a pre-formatted line.
    if (event.t === "trade" && event.direction && event.asset && event.price) {
      const arrow = event.direction === "buy" ? "\u2191" : "\u2193";
      return (
        <div className="text-yellow-300">
          {`  ${arrow} ${event.direction.toUpperCase()} ${event.asset} @ $${fmtLite(event.price, 2)}`}
          {event.position !== undefined ? `  pos=${fmtLite(event.position, 2)}` : ""}
          {event.equity !== undefined ? `  equity=$${fmtLite(event.equity, 0)}` : ""}
        </div>
      );
    }
    if (event.t === "progress" && event.pct !== undefined) {
      const pct = Math.round(event.pct);
      const bar = "\u2588".repeat(Math.round(pct / 5));
      const space = "\u2591".repeat(20 - bar.length);
      return (
        <div className="text-neutral-300">
          {`  [${bar}${space}] ${fmtLite(event.pct, 1)}%  bar ${event.bar || 0}/${event.total || 0}  equity=$${fmtLite(event.equity, 0)}`}
        </div>
      );
    }
    return null;
  }

  return <div className={colorClass}>{line}</div>;
}
