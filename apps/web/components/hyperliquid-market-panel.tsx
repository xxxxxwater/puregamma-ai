"use client";

import { ChevronDown, ChevronUp, Radio } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type Locale = "en" | "zh";

type Instrument = {
  id: string;
  symbol: string;
  venue: string;
  leverage: number;
};

type Candle = {
  o: number;
  c: number;
  v: number;
  updatedAt: number;
};

type AssetContext = {
  markPx?: number;
  dayNtlVlm?: number;
  openInterest?: number;
  funding?: number;
  updatedAt: number;
};

type MarketState = Record<string, { candle?: Candle; context?: AssetContext }>;

const WS_URL = `${(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/^http/, "ws")}/market/hyperliquid/stream`;

const INSTRUMENTS: Instrument[] = [
  { id: "xyz:CL", symbol: "WTIOIL-USDC", venue: "xyz", leverage: 20 },
  { id: "xyz:BRENTOIL", symbol: "BRENTOIL-USDC", venue: "xyz", leverage: 20 },
  { id: "xyz:SKHX", symbol: "SKHYNIX-USDC", venue: "xyz", leverage: 10 },
  { id: "xyz:SP500", symbol: "S&P500-USDC", venue: "xyz", leverage: 50 },
  { id: "xyz:XYZ100", symbol: "XYZ100-USDC", venue: "xyz", leverage: 30 },
  { id: "xyz:MU", symbol: "MU-USDC", venue: "xyz", leverage: 10 },
  { id: "xyz:SNDK", symbol: "SNDK-USDC", venue: "xyz", leverage: 10 },
  { id: "xyz:DRAM", symbol: "DRAM-USDC", venue: "xyz", leverage: 20 },
  { id: "xyz:SPCX", symbol: "SPCX-USDC", venue: "xyz", leverage: 20 },
  { id: "xyz:SKHY", symbol: "SKHY-USDC", venue: "xyz", leverage: 10 },
  { id: "xyz:EWY", symbol: "EWY-USDC", venue: "xyz", leverage: 20 },
  { id: "BTC", symbol: "BTC-USDC", venue: "Hyperliquid", leverage: 40 },
  { id: "ETH", symbol: "ETH-USDC", venue: "Hyperliquid", leverage: 25 },
  { id: "HYPE", symbol: "HYPE-USDC", venue: "Hyperliquid", leverage: 10 },
  { id: "ZEC", symbol: "ZEC-USDC", venue: "Hyperliquid", leverage: 10 },
  { id: "SOL", symbol: "SOL-USDC", venue: "Hyperliquid", leverage: 20 },
  { id: "CASHCAT", symbol: "CASHCAT-USDC", venue: "Hyperliquid", leverage: 3 },
  { id: "ONDO", symbol: "ONDO-USDC", venue: "Hyperliquid", leverage: 10 }
];

function number(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function price(value?: number): string {
  if (value === undefined) return "--";
  const digits = value >= 1000 ? 1 : value >= 1 ? 2 : value >= 0.1 ? 4 : 6;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function compactUsd(value?: number): string {
  if (value === undefined) return "--";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

// Official colored coin icons are self-hosted under /coins (downloaded from
// Hyperliquid's official icon set). Synthetic XYZ assets (CL, S&P500, ...)
// have no icon upstream: they render a per-asset colored gradient badge.
function assetCoin(instrumentId: string): string {
  return instrumentId.startsWith("xyz:") ? instrumentId.slice(4) : instrumentId;
}

const SYNTH_GRADIENTS: Record<string, string> = {
  CL: "from-sky-400 to-blue-600",
  BRENTOIL: "from-indigo-400 to-violet-600",
  SKHYNIX: "from-amber-400 to-orange-600",
  "S&P500": "from-emerald-400 to-teal-600",
  XYZ100: "from-rose-400 to-red-600",
  MU: "from-fuchsia-400 to-purple-600",
  SNDK: "from-cyan-400 to-sky-600",
  DRAM: "from-lime-400 to-green-600",
  SPCX: "from-orange-400 to-amber-600",
  SKHY: "from-violet-400 to-indigo-600",
  EWY: "from-teal-400 to-emerald-600",
};

function SynthBadge({ coin }: { coin: string }) {
  const gradient = SYNTH_GRADIENTS[coin] ?? "from-slate-400 to-slate-600";
  return (
    <span
      aria-hidden
      className={`grid h-6 w-6 shrink-0 place-items-center rounded-full bg-gradient-to-br ${gradient} text-[10px] font-bold text-white`}
    >
      {coin.charAt(0)}
    </span>
  );
}

function AssetIcon({ coin }: { coin: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <SynthBadge coin={coin} />;
  }
  return (
    <img
      src={`/coins/${coin}.svg`}
      alt={coin}
      width={24}
      height={24}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-6 w-6 shrink-0 rounded-full object-cover"
    />
  );
}

function percent(value?: number): string {
  if (value === undefined) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function timestamp(value?: number): string {
  if (!value) return "--";
  return new Date(value).toISOString().slice(11, 19);
}

export function HyperliquidMarketPanel({ locale }: { locale: Locale }) {
  const [isOpen, setIsOpen] = useState(true);
  const [status, setStatus] = useState<"connecting" | "live" | "reconnecting">("connecting");
  const [market, setMarket] = useState<MarketState>({});
  const retryTimer = useRef<ReturnType<typeof setTimeout>>();
  const retryCount = useRef(0);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      setStatus(retryCount.current ? "reconnecting" : "connecting");
      socket = new WebSocket(WS_URL);

      socket.onopen = () => {
        retryCount.current = 0;
        setStatus("connecting");
      };

      socket.onmessage = (event) => {
        let message: { channel?: string; data?: unknown };
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        const now = Date.now();
        if (message.channel === "candle") {
          const candles = Array.isArray(message.data) ? message.data : [message.data];
          setMarket((current) => {
            const next = { ...current };
            for (const item of candles) {
              if (!item || typeof item !== "object") continue;
              const candle = item as Record<string, unknown>;
              const coin = String(candle.s || "");
              if (!INSTRUMENTS.some((instrument) => instrument.id === coin)) continue;
              next[coin] = {
                ...next[coin],
                candle: { o: number(candle.o) ?? 0, c: number(candle.c) ?? 0, v: number(candle.v) ?? 0, updatedAt: now }
              };
            }
            return next;
          });
          setStatus("live");
        }
        if (message.channel === "activeAssetCtx" && message.data && typeof message.data === "object") {
          const data = message.data as { coin?: string; ctx?: Record<string, unknown> };
          const coin = data.coin || "";
          if (!INSTRUMENTS.some((instrument) => instrument.id === coin)) return;
          setMarket((current) => ({
            ...current,
            [coin]: {
              ...current[coin],
              context: {
                markPx: number(data.ctx?.markPx),
                dayNtlVlm: number(data.ctx?.dayNtlVlm),
                openInterest: number(data.ctx?.openInterest),
                funding: number(data.ctx?.funding),
                updatedAt: now
              }
            }
          }));
          setStatus("live");
        }
        if (message.channel === "marketFeedError") socket?.close();
      };

      socket.onclose = () => {
        if (stopped) return;
        retryCount.current += 1;
        const delay = Math.min(15_000, 1_000 * 2 ** Math.min(retryCount.current, 4));
        retryTimer.current = setTimeout(connect, delay);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer.current) clearTimeout(retryTimer.current);
      socket?.close();
    };
  }, []);

  const rows = useMemo(() => INSTRUMENTS.map((instrument) => {
    const entry = market[instrument.id];
    const candle = entry?.candle;
    const context = entry?.context;
    const last = context?.markPx ?? candle?.c;
    const change = candle && candle.o ? ((candle.c - candle.o) / candle.o) * 100 : undefined;
    const openInterestUsd = context?.openInterest !== undefined && last !== undefined ? context.openInterest * last : undefined;
    return { instrument, candle, context, last, change, openInterestUsd };
  }).sort((a, b) => (b.context?.dayNtlVlm ?? -1) - (a.context?.dayNtlVlm ?? -1)), [market]);

  const copy = locale === "zh"
    ? { title: "Autopilot 实时市场观察", subtitle: "Hyperliquid · 15 分钟 K 线", collapse: "收起行情列表", expand: "展开行情列表", price: "最新", change: "15 分钟", volume: "24h 成交额", oi: "未平仓", funding: "资金费率", updated: "UTC" }
    : { title: "Autopilot live market watch", subtitle: "Hyperliquid · 15-minute candles", collapse: "Collapse market list", expand: "Expand market list", price: "Last", change: "15m", volume: "24h notional", oi: "Open interest", funding: "Funding", updated: "UTC" };

  return (
    <section className="overflow-hidden border border-border-pg bg-bg-panel rounded-xl">
      <div className="flex items-center justify-between gap-4 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">
            <Radio className={status === "live" ? "h-3.5 w-3.5 text-status-positive" : "h-3.5 w-3.5 text-status-warning"} />
            <span>{status === "live" ? "LIVE" : status === "reconnecting" ? "RECONNECTING" : "CONNECTING"}</span>
          </div>
          <h2 className="mt-1 text-lg font-semibold text-text-pg">{copy.title}</h2>
          <p className="mt-1 text-xs text-text-pg-muted">{copy.subtitle}</p>
        </div>
        <button type="button" onClick={() => setIsOpen((open) => !open)} className="grid h-9 w-9 shrink-0 place-items-center border border-border-pg text-text-pg-muted transition hover:border-border-pg-strong hover:text-text-pg rounded-lg" aria-expanded={isOpen} aria-label={isOpen ? copy.collapse : copy.expand} title={isOpen ? copy.collapse : copy.expand}>
          {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>
      {isOpen ? <div className="overflow-x-auto border-t border-border-pg">
        <table className="w-full min-w-[980px] font-mono text-sm">
          <thead className="bg-bg-panel-muted text-left text-[10px] uppercase text-text-pg-dim">
            <tr><th className="px-4 py-2 font-medium">{locale === "zh" ? "合约" : "Contract"}</th><th className="px-3 py-2 text-right font-medium">{copy.price}</th><th className="px-3 py-2 text-right font-medium">{copy.change}</th><th className="px-3 py-2 text-right font-medium">{copy.volume}</th><th className="px-3 py-2 text-right font-medium">{copy.oi}</th><th className="px-3 py-2 text-right font-medium">{copy.funding}</th><th className="px-4 py-2 text-right font-medium">{copy.updated}</th></tr>
          </thead>
          <tbody>
            {rows.map(({ instrument, candle, context, last, change, openInterestUsd }) => <tr key={instrument.id} className="border-t border-border-pg/70 hover:bg-bg-panel-muted">
              <td className="px-4 py-3"><div className="flex items-center gap-2.5"><AssetIcon coin={assetCoin(instrument.id)} /><span className="font-semibold text-text-pg">{instrument.symbol}</span></div><div className="mt-1 text-[10px] text-text-pg-dim">{instrument.leverage}x · {instrument.venue}</div></td>
              <td key={`px-${last ?? "na"}`} className="market-cell-flash px-3 py-3 text-right text-text-pg">{price(last)}</td>
              <td key={`chg-${last ?? "na"}`} className="market-cell-flash px-3 py-3 text-right">
                <span className="inline-block border border-border-pg-strong bg-pg-white px-1.5 py-0.5 font-semibold text-pg-black rounded-lg">{percent(change)}</span>
              </td>
              <td className="px-3 py-3 text-right text-text-pg-muted">{compactUsd(context?.dayNtlVlm)}</td>
              <td className="px-3 py-3 text-right text-text-pg-muted">{compactUsd(openInterestUsd)}</td>
              <td className="px-3 py-3 text-right text-text-pg-muted">{context?.funding === undefined ? "--" : `${(context.funding * 100).toFixed(4)}%`}</td>
              <td className="px-4 py-3 text-right text-text-pg-dim">{timestamp(Math.max(candle?.updatedAt || 0, context?.updatedAt || 0))}</td>
            </tr>)}
          </tbody>
        </table>
      </div> : null}
    </section>
  );
}
