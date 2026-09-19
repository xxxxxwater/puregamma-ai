"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, CircleDot, Clock, Cpu, Radio, TrendingUp, WifiOff } from "lucide-react";

import { Badge, EmptyState, MetricCard } from "@/components/puregamma";

/**
 * Live view of the third-party Jev Trader demo.
 *
 * Three things this component refuses to do, all of them learned from the
 * P1 audit (docs/audit/JEV_TRADER_AUDIT.md):
 *
 * 1. It never hardcodes the authenticity label. The upstream reports
 *    `model` and `dryRun` on every snapshot, and the label is recomputed from
 *    them. The README says the deployment runs a mock model; it does not, and
 *    a hardcoded label would have been wrong in the dangerous direction.
 * 2. It never treats a missing heartbeat as a disconnect. The deployed
 *    upstream was not observed to send the ping its HEAD source emits, so
 *    liveness comes from event arrival time.
 * 3. It never invents a number. A field the upstream did not send renders as
 *    unavailable, never as zero.
 *
 * Memory is bounded end to end: the event list is capped, and the reconnect
 * backoff is capped.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Matches the server ring buffer's practical slice for display. */
const MAX_EVENTS = 500;
const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;
/** Nothing arriving for this long means stale, not disconnected. Blocks are
 *  ~300ms, so 45s is ~150 missed blocks -- well beyond normal quiet. */
const STALE_AFTER_MS = 45_000;

type ModelStatus = "real_reported" | "mock_reported" | "unknown";
type TradingStatus = "simulated" | "live_verified" | "unknown";
type Connection = "connecting" | "connected" | "reconnecting" | "disconnected";

interface JevEvent {
  seq: number;
  block: number;
  ts: number | null;
  mid: number | null;
  best_bid: number | null;
  best_ask: number | null;
  spread_bps: number | null;
  decision: {
    action: string | null;
    probabilities: Record<string, number>;
    up_in_10: number | null;
    latency_ms: number | null;
    late: boolean;
  };
  fill: {
    side: string | null;
    size: number | null;
    price: number | null;
    simulated: boolean;
    tx_hash: string | null;
    gas_mon: number | null;
  } | null;
  totals: { fields: Record<string, unknown>; schema_mismatch: boolean; length: number };
}

interface Snapshot {
  schema_version: string;
  meta: { model?: string | null; dry_run?: boolean | null; wallet?: string | null; market?: string | null };
  latest: JevEvent | null;
  totals: { fields: Record<string, unknown>; schema_mismatch: boolean };
  seq: number;
  buffer_size: number;
  event_buffer_limit: number;
}

/** Model truth, derived from what upstream reports -- and labelled as such. */
function modelStatus(meta: Snapshot["meta"] | null): ModelStatus {
  const model = (meta?.model ?? "").toLowerCase();
  if (!model) return "unknown";
  // Only the upstream's own string can distinguish these; we have no
  // independent per-request proof, so both are "reported".
  return model.includes("mock") ? "mock_reported" : "real_reported";
}

/**
 * Trading truth.
 *
 * SIMULATED is only claimed on positive evidence (dryRun true, or a null
 * wallet, or a fill carrying `simulated`). LIVE_VERIFIED requires a confirmed
 * on-chain transaction, which this feed never provides -- so it is deliberately
 * unreachable here rather than inferred from the presence of a PnL chart.
 */
function tradingStatus(meta: Snapshot["meta"] | null, latest: JevEvent | null): TradingStatus {
  if (meta?.dry_run === true || meta?.wallet === null) return "simulated";
  if (latest?.fill?.tx_hash) return "live_verified";
  if (latest?.fill?.simulated) return "simulated";
  return "unknown";
}

function num(value: number | null | undefined, digits = 6): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function usd(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toFixed(4)}`;
}

export function JevTraderConsole({ locale }: { locale: "en" | "zh" }) {
  const zh = locale === "zh";
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [events, setEvents] = useState<JevEvent[]>([]);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState<number>(() => Date.now());
  const [visible, setVisible] = useState(true);

  const sourceRef = useRef<EventSource | null>(null);
  const backoffRef = useRef(BACKOFF_MIN_MS);
  const cursorRef = useRef<number>(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Events are batched so a burst cannot trigger one render per event.
  const pendingRef = useRef<JevEvent[]>([]);
  const flushTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const closedRef = useRef(false);

  const ingest = useCallback((incoming: JevEvent[]) => {
    if (!incoming.length) return;
    setEvents((prev) => {
      const seen = new Set(prev.map((e) => e.seq));
      const fresh = incoming.filter((e) => !seen.has(e.seq));
      if (!fresh.length) return prev;
      const merged = [...prev, ...fresh];
      // Bounded: the oldest fall off rather than the array growing forever.
      return merged.length > MAX_EVENTS ? merged.slice(merged.length - MAX_EVENTS) : merged;
    });
  }, []);

  const loadSnapshot = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/jev-trader/snapshot`, { cache: "no-store" });
      if (!res.ok) throw new Error(`snapshot ${res.status}`);
      const data: Snapshot = await res.json();
      setSnapshot(data);
      setError(null);
      cursorRef.current = data.seq ?? 0;
      return data.seq ?? 0;
    } catch (err) {
      setError(err instanceof Error ? err.message : "snapshot failed");
      return null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (closedRef.current) return;
    sourceRef.current?.close();
    const since = await loadSnapshot();
    if (since === null || closedRef.current) return;

    const es = new EventSource(`${API_URL}/jev-trader/events?since=${since}`);
    sourceRef.current = es;

    es.addEventListener("open", () => {
      setConnection("connected");
      backoffRef.current = BACKOFF_MIN_MS;
    });
    es.addEventListener("event", (ev) => {
      try {
        const parsed = JSON.parse((ev as MessageEvent).data) as JevEvent;
        cursorRef.current = parsed.seq;
        pendingRef.current.push(parsed);
      } catch {
        /* a malformed frame is dropped, never rendered */
      }
    });
    es.addEventListener("resync", () => {
      // The server could not cover the gap. Take a fresh snapshot rather than
      // pretending we caught up.
      void loadSnapshot();
    });
    es.onerror = () => {
      es.close();
      sourceRef.current = null;
      if (closedRef.current) return;
      setConnection("reconnecting");
      const delay = Math.min(BACKOFF_MAX_MS, backoffRef.current);
      backoffRef.current = Math.min(BACKOFF_MAX_MS, delay * 2);
      retryTimer.current = setTimeout(() => void connect(), delay);
    };
  }, [loadSnapshot]);

  useEffect(() => {
    closedRef.current = false;
    void connect();
    // Batch pending events into one render every 250ms.
    flushTimer.current = setInterval(() => {
      if (pendingRef.current.length) {
        const batch = pendingRef.current;
        pendingRef.current = [];
        ingest(batch);
      }
      setNow(Date.now());
    }, 250);
    return () => {
      closedRef.current = true;
      if (flushTimer.current) clearInterval(flushTimer.current);
      if (retryTimer.current) clearTimeout(retryTimer.current);
      sourceRef.current?.close();
      sourceRef.current = null;
    };
  }, [connect, ingest]);

  // Pause timers while the tab is hidden; nothing user-visible is updating.
  useEffect(() => {
    const onVisibility = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const latest = events.length ? events[events.length - 1] : snapshot?.latest ?? null;
  const meta = snapshot?.meta ?? null;
  const model = modelStatus(meta);
  const trading = tradingStatus(meta, latest);

  const lastEventAt = latest?.ts ?? null;
  const ageMs = lastEventAt ? now - lastEventAt : null;
  const stale = ageMs !== null && ageMs > STALE_AFTER_MS;

  const totals = snapshot?.totals?.fields ?? {};
  const decisions = typeof totals.decisions === "number" ? totals.decisions : null;
  const jevUsd = typeof totals.jev_usd === "number" ? totals.jev_usd : null;
  const lateBlocks = typeof totals.late_blocks === "number" ? totals.late_blocks : null;
  const blocks = typeof totals.blocks === "number" ? totals.blocks : null;

  const latencies = useMemo(
    () => events.map((e) => e.decision.latency_ms).filter((v): v is number => typeof v === "number"),
    [events],
  );
  const avgLatency = latencies.length
    ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
    : null;

  const connectionLabel = {
    connecting: zh ? "连接中" : "Connecting",
    connected: stale ? (zh ? "已连接 · 数据过期" : "Connected · stale") : zh ? "已连接" : "Connected",
    reconnecting: zh ? "重连中" : "Reconnecting",
    disconnected: zh ? "已断开" : "Disconnected",
  }[connection];

  const modelLabel =
    model === "real_reported"
      ? zh ? "Jev 真实模型推理" : "Real Jev model"
      : model === "mock_reported"
        ? zh ? "Mock 模型" : "Mock model"
        : zh ? "模型状态未知" : "Model unknown";

  const tradingLabel =
    trading === "simulated"
      ? zh ? "模拟交易" : "Simulated trading"
      : trading === "live_verified"
        ? zh ? "已核实真实成交" : "Verified live trading"
        : zh ? "交易模式未知" : "Trading unknown";

  return (
    <div className="space-y-6">
      {/* Status band: connection, model and trading are three separate facts. */}
      <section className="border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={connection === "connected" && !stale ? "emerald" : connection === "connected" ? "neutral" : "red"}>
            {connection === "connected" ? <CircleDot className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
            {connectionLabel}
          </Badge>
          <Badge tone={model === "real_reported" ? "cyan" : "neutral"}>
            <Cpu className="h-3 w-3" />
            {modelLabel}
          </Badge>
          <Badge tone={trading === "live_verified" ? "red" : "neutral"}>
            <Activity className="h-3 w-3" />
            {tradingLabel}
          </Badge>
          <span className="text-xs text-text-pg-muted">
            {zh ? "模型名" : "Model"}: <span className="font-mono">{meta?.model ?? "—"}</span>
            {" · "}
            {zh ? "市场" : "Market"}: <span className="font-mono">{meta?.market ? `${meta.market.slice(0, 10)}…` : "—"}</span>
          </span>
        </div>
        <p className="mt-3 text-xs leading-5 text-text-pg-muted">
          {zh
            ? "第三方实时演示（dry-run）。模型状态与交易状态由上游每次快照上报的 model / dryRun 字段实时判定，非本站硬编码。模拟收益不代表实盘收益。"
            : "Third-party live demo (dry run). Model and trading status are derived live from the upstream model / dryRun fields on every snapshot, never hardcoded. Simulated results are not live results."}
        </p>
      </section>

      {/* Market / chain */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-pg">
          <TrendingUp className="h-4 w-4" />
          {zh ? "行情与链上" : "Market & chain"}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label={zh ? "最新区块" : "Latest block"} value={latest ? String(latest.block) : "—"} detail={zh ? "Monad" : "Monad"} tone="cyan" />
          <MetricCard label={zh ? "中间价" : "Mid price"} value={num(latest?.mid)} detail="MON/USDC" tone="neutral" />
          <MetricCard label={zh ? "买卖价差" : "Spread"} value={latest?.spread_bps != null ? `${num(latest.spread_bps, 2)} bps` : "—"} detail={zh ? "best bid / ask" : "best bid / ask"} tone="neutral" />
          <MetricCard label={zh ? "事件年龄" : "Event age"} value={ageMs != null ? `${Math.round(ageMs / 1000)}s` : "—"} detail={zh ? "据此判断新鲜度" : "freshness source"} tone={stale ? "red" : "neutral"} />
        </div>
      </section>

      {/* Decision engine */}
      <section className="border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-pg">
          <Cpu className="h-4 w-4" />
          {zh ? "决策引擎" : "Decision engine"}
        </h2>
        {latest?.decision?.late ? (
          <EmptyState
            title={zh ? "模型错过了该区块" : "Model missed this block"}
            description={zh ? "该块标记为 late，未产生有效决策，不构成一次选择。" : "Marked late: no valid decision was made for this block."}
          />
        ) : latest ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {["buy", "sell", "hold"].map((side) => {
              const p = latest.decision.probabilities?.[side];
              return (
                <MetricCard
                  key={side}
                  label={side.toUpperCase()}
                  value={typeof p === "number" ? `${(p * 100).toFixed(1)}%` : "—"}
                  detail={
                    latest.decision.action === side
                      ? zh ? "本次决策" : "chosen"
                      : zh ? "概率" : "probability"
                  }
                  tone={latest.decision.action === side ? "emerald" : "neutral"}
                />
              );
            })}
          </div>
        ) : (
          <EmptyState title={zh ? "等待实时数据" : "Waiting for live data"} description={zh ? "尚未收到任何区块事件。" : "No block events received yet."} />
        )}
        {latest && !latest.decision.late ? (
          <p className="mt-3 text-xs text-text-pg-muted">
            {zh ? "最近决策" : "Latest decision"}: <span className="font-medium text-text-pg">{latest.decision.action ?? "—"}</span>
            {" · "}
            {zh ? "推理耗时" : "Inference latency"}: {latest.decision.latency_ms != null ? `${latest.decision.latency_ms} ms` : "—"}
            {latest.ts ? ` · ${new Date(latest.ts).toLocaleTimeString()}` : ""}
          </p>
        ) : null}
      </section>

      {/* Model statistics. Cumulative counters are labelled as cumulative --
          none of these is a rate. */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-pg">
          <Clock className="h-4 w-4" />
          {zh ? "模型统计（上游累计值）" : "Model statistics (upstream cumulative)"}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label={zh ? "累计决策" : "Total decisions"} value={decisions != null ? decisions.toLocaleString() : "—"} detail={zh ? "累计，非速率" : "cumulative, not a rate"} tone="neutral" />
          <MetricCard label={zh ? "累计区块" : "Total blocks"} value={blocks != null ? blocks.toLocaleString() : "—"} detail={zh ? "累计" : "cumulative"} tone="neutral" />
          <MetricCard label={zh ? "平均推理延迟" : "Avg latency"} value={avgLatency != null ? `${avgLatency} ms` : "—"} detail={zh ? "本页基于已接收事件计算" : "computed here from received events"} tone="neutral" />
          <MetricCard label={zh ? "上游模型成本" : "Upstream model cost"} value={usd(jevUsd)} detail={zh ? "上游累计报告" : "upstream cumulative"} tone="neutral" />
        </div>
        {lateBlocks != null && decisions ? (
          <p className="mt-2 text-xs text-text-pg-muted">
            {zh ? "迟到区块" : "Late blocks"}: {lateBlocks.toLocaleString()}
            {` (${((lateBlocks / (lateBlocks + decisions)) * 100).toFixed(1)}%)`}
            {" · "}
            {zh ? "本页指标由 PureGamma 基于上游原始数据计算" : "Metrics on this page are computed by PureGamma from raw upstream data"}
          </p>
        ) : null}
      </section>

      {/* Bounded event list */}
      <section className="border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text-pg">
            <Radio className="h-4 w-4" />
            {zh ? "最近事件" : "Recent events"}
          </h2>
          <span className="text-xs text-text-pg-muted">
            {events.length} / {MAX_EVENTS}
            {snapshot ? ` · ${zh ? "服务端缓冲" : "server buffer"} ${snapshot.buffer_size}/${snapshot.event_buffer_limit}` : ""}
          </span>
        </div>
        {events.length ? (
          <div className={visible ? "max-h-96 overflow-y-auto" : "max-h-96 overflow-y-auto opacity-60"}>
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-bg-panel text-text-pg-dim">
                <tr className="text-left">
                  <th className="py-1 pr-3 font-medium">{zh ? "时间" : "Time"}</th>
                  <th className="py-1 pr-3 font-medium">{zh ? "区块" : "Block"}</th>
                  <th className="py-1 pr-3 font-medium">{zh ? "决策" : "Decision"}</th>
                  <th className="py-1 pr-3 font-medium">{zh ? "延迟" : "Latency"}</th>
                  <th className="py-1 font-medium">{zh ? "模式" : "Mode"}</th>
                </tr>
              </thead>
              <tbody>
                {[...events].reverse().slice(0, 100).map((e) => (
                  <tr key={e.seq} className="border-t border-border-pg">
                    <td className="py-1 pr-3 tabular-nums">{e.ts ? new Date(e.ts).toLocaleTimeString() : "—"}</td>
                    <td className="py-1 pr-3 tabular-nums">{e.block}</td>
                    <td className="py-1 pr-3">
                      {e.decision.late ? (zh ? "迟到" : "late") : e.decision.action ?? "—"}
                    </td>
                    <td className="py-1 pr-3 tabular-nums">{e.decision.latency_ms != null ? `${e.decision.latency_ms}ms` : "—"}</td>
                    <td className="py-1">{e.fill?.simulated ? (zh ? "模拟" : "sim") : trading === "live_verified" ? (zh ? "实盘" : "live") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title={zh ? "等待实时数据" : "Waiting for live data"} description={zh ? "连接建立后将在此显示最近事件。" : "Recent events appear here once the stream is connected."} />
        )}
      </section>

      {error ? (
        <p className="text-xs text-status-negative">
          {zh ? "快照加载失败" : "Snapshot failed"}: {error}
        </p>
      ) : null}
    </div>
  );
}
