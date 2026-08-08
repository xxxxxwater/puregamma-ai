"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Terminal } from "lucide-react";
import { API_URL } from "@/lib/api";

const MAX_TERMINAL_LINES = 2_000;

interface LogEvent {
  t: string;
  ts?: string;
  seq?: number;
  line?: string;
  bar?: number;
  total?: number;
  pct?: number;
  direction?: string;
  price?: number;
  equity?: number;
  position?: number;
  asset?: string;
}

interface StreamRun {
  id: string;
  status: string;
  isLegacy?: boolean;
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
  const runId = run?.id ?? null;
  const [lines, setLines] = useState<LogEvent[]>([]);
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const [streamEnded, setStreamEnded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const streaming = useMemo(
    () => run !== null && !isTerminal(run.status),
    [run]
  );

  // A new run opens immediately.  A finished run remains readable for 30
  // seconds, then folds back into its compact header.
  useEffect(() => {
    if (!run) return;
    if (!isTerminal(run.status)) {
      setOpen(true);
      return;
    }
    const timer = window.setTimeout(() => setOpen(false), 30_000);
    return () => window.clearTimeout(timer);
  }, [runId, run?.status]);

  // Each run has one EventSource.  Redis retains a bounded transcript, so a
  // late mount or a reconnect can replay the missing lines without duplicate
  // React effects reconnecting to the same stream.
  useEffect(() => {
    if (!runId || run?.isLegacy) return;

    setLines([]);
    setConnected(false);
    setStreamEnded(false);

    const evt = new EventSource(`${API_URL}/backtest-lab/runs/${runId}/stream`, {
      withCredentials: true,
    });
    eventSourceRef.current = evt;

    evt.addEventListener("open", () => setConnected(true));
    evt.addEventListener("message", (message) => {
      try {
        const parsed: LogEvent = JSON.parse((message as MessageEvent<string>).data);
        setLines((previous) => [...previous, parsed].slice(-MAX_TERMINAL_LINES));
        setConnected(true);
        if (parsed.t === "close") {
          setStreamEnded(true);
          setConnected(false);
          evt.close();
          if (eventSourceRef.current === evt) eventSourceRef.current = null;
        }
      } catch {
        // Ignore a malformed message and keep the stream available for the
        // next valid event.
      }
    });
    evt.addEventListener("error", () => {
      // EventSource retries transient network faults by itself.  A terminal
      // `close` event above intentionally disables that reconnect behavior.
      setConnected(false);
    });

    return () => {
      evt.close();
      if (eventSourceRef.current === evt) eventSourceRef.current = null;
    };
  }, [runId, run?.isLegacy]);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [lines]);

  if (!run) {
    return (
      <div className="border border-border-pg bg-bg-panel p-4 text-xs text-text-pg-dim rounded-xl">
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
      onClick={() => setOpen((previous) => !previous)}
      aria-expanded={open}
      className="flex w-full items-center justify-between border border-border-pg bg-bg-panel px-4 py-2.5 text-left text-xs font-semibold rounded-lg"
    >
      <span className="flex items-center gap-2">
        <Terminal className="h-4 w-4" />
        {zh ? "回测终端" : "Backtest Terminal"}
        {streaming ? (
          <span className="inline-flex items-center gap-1 text-status-positive">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-status-positive" />
            {zh ? "运行中" : "Running"}
          </span>
        ) : streamEnded ? (
          <span className="text-text-pg-dim">{zh ? "已结束" : "Finished"}</span>
        ) : connected ? (
          <span className="text-text-pg-dim">{zh ? "连接中" : "Connected"}</span>
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
        role="log"
        aria-live="polite"
        className="max-h-96 overflow-y-auto border-x border-b border-border-pg bg-[#0a0a0a] px-4 py-3 font-mono text-[11px] leading-[1.55] rounded-xl"
      >
        {lines.length === 0 ? (
          <span className="text-neutral-600">
            {streaming
              ? `█ ${zh ? "等待工作进程..." : "Waiting for worker..."}`
              : zh
                ? "无可用终端输出"
                : "No terminal output available"}
          </span>
        ) : (
          lines.map((event, index) => (
            <TerminalLine key={`${event.seq ?? "event"}-${index}`} event={event} />
          ))
        )}
        {streaming && !streamEnded ? (
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
        return "font-semibold text-green-300";
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

  if (event.line) return <div className={colorClass}>{event.line}</div>;

  // Structured fallback keeps the terminal useful if a newer worker omits a
  // pre-formatted line while this client is still deployed.
  if (event.t === "trade" && event.direction && event.asset && event.price !== undefined) {
    const arrow = event.direction === "buy" ? "↑" : "↓";
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
    const filled = Math.min(20, Math.max(0, Math.round(pct / 5)));
    return (
      <div className="text-neutral-300">
        {`  [${"█".repeat(filled)}${"░".repeat(20 - filled)}] ${fmtLite(event.pct, 1)}%  bar ${event.bar || 0}/${event.total || 0}  equity=$${fmtLite(event.equity, 0)}`}
      </div>
    );
  }
  return null;
}
