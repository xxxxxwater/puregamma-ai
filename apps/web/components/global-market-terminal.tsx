"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { getMessageNamespace } from "@/lib/translations";
import { getGlobalMarket, type GlobalMarketRow, type GlobalMarketSnapshot } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const GROUP_ORDER = ["nasdaq_top", "metals", "forex", "energy"];

// Brand colors for equity tickers (self-hosted colored marks, TradingView
// style). Unknown tickers fall back to a neutral gradient badge.
const BRAND_COLORS: Record<string, string> = {
  NVDA: "#76B900",
  MSFT: "#00A4EF",
  AAPL: "#A2AAAD",
  PLTR: "#FF6B1A",
  AMZN: "#FF9900",
  TSLA: "#E31937",
  META: "#0866FF",
  GOOGL: "#4285F4",
  GOOG: "#4285F4",
  NFLX: "#E50914",
  AMD: "#ED1C24",
  INTC: "#0071C5",
  ORCL: "#F80000",
  CRM: "#00A1E0",
  AVGO: "#CC092F",
  MU: "#00B5CC",
  SMCI: "#D65F00",
  COIN: "#0052FF",
  SHOP: "#95BF47",
  UBER: "#111111",
  SNAP: "#FFC107",
  PINS: "#E60023",
  SQ: "#001F5F",
  PYPL: "#003087",
  DIS: "#113CCF",
  JPM: "#003DA5",
  BAC: "#012169",
  XOM: "#E21E25",
  CVX: "#F2A900",
  JNJ: "#D4145A",
  PFE: "#008BD0",
  UNH: "#0057B8",
  WMT: "#0071DC",
  PG: "#003DA5",
  KO: "#F40009",
  PEP: "#01427B",
  MCD: "#FFBC0D",
  NKE: "#111111",
  BA: "#0033A1",
  CAT: "#F5A800",
  GE: "#0057D8",
  F: "#1E5AA8",
  GM: "#1E5AA8",
};

function normalizeTicker(symbol: string): string {
  return symbol.replace(/DLY$/, "").replace(/=X$/, "").replace(/=F$/, "");
}

function shade(hex: string, amount: number): string {
  const n = parseInt(hex.replace("#", ""), 16);
  const r = Math.min(255, Math.max(0, ((n >> 16) & 255) + amount));
  const g = Math.min(255, Math.max(0, ((n >> 8) & 255) + amount));
  const b = Math.min(255, Math.max(0, (n & 255) + amount));
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

const FX_COLORS: Record<string, string> = {
  EUR: "#003399",
  USD: "#0B3D91",
  JPY: "#BC002D",
  GBP: "#012169",
  AUD: "#00843D",
  CHF: "#D52B1E",
  CAD: "#D80621",
  CNY: "#DE2910",
};

const OIL_PATH = "M12 2.5 C12 2.5 6.5 10.5 6.5 14.5 a5.5 5.5 0 0 0 11 0 C17.5 10.5 12 2.5 12 2.5 Z";
const FLAME_PATH = "M12 2 C12 5 14.8 7.5 14.8 11 a2.8 2.8 0 0 1 -5.6 0 C9.2 7.5 12 5 12 2 Z M12 10.5 c1.2 1 1.6 1.8 1.6 2.6 a1.6 1.6 0 0 1 -3.2 0 C10.4 12.3 10.8 11.5 12 10.5 Z";

function MarketLogo({ row }: { row: GlobalMarketRow }) {
  const ticker = normalizeTicker(row.symbol).toUpperCase();
  const lower = ticker.toLowerCase();
  const id = `mk-${ticker.toLowerCase()}`;

  // Forex pairs: two-tone gradient with the currency codes.
  const fxMatch = /^([A-Z]{3})([A-Z]{3})$/.exec(ticker);
  if (fxMatch || row.asset_type === "forex") {
    const left = (fxMatch?.[1] ?? (lower.includes("eur") ? "EUR" : lower.includes("jpy") ? "JPY" : lower.includes("gbp") ? "GBP" : lower.includes("aud") ? "AUD" : "USD"));
    const right = (fxMatch?.[2] ?? "USD");
    const lc = FX_COLORS[left] ?? "#3B82F6";
    const rc = FX_COLORS[right] ?? "#64748B";
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden className="h-6 w-6 shrink-0 rounded-full">
        <defs>
          <linearGradient id={`${id}-fx`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={lc} />
            <stop offset="1" stopColor={rc} />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="22" height="22" rx="11" fill={`url(#${id}-fx)`} />
        <text x="7.4" y="15.2" textAnchor="middle" fontSize="7" fontWeight="700" fill="#fff">{left}</text>
        <text x="16.6" y="15.2" textAnchor="middle" fontSize="7" fontWeight="700" fill="#fff" opacity="0.9">{right}</text>
      </svg>
    );
  }

  // Commodities: gold/silver bars and oil/gas marks.
  if (lower === "gc" || lower === "si" || row.asset_type === "metals" || lower.includes("gold") || lower.includes("silver")) {
    const gold = lower === "gc" || lower.includes("gold");
    const c1 = gold ? "#F6C453" : "#C0C8D2";
    const c2 = gold ? "#B8860B" : "#8A94A6";
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden className="h-6 w-6 shrink-0 rounded-full">
        <defs>
          <linearGradient id={`${id}-bar`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={c1} />
            <stop offset="1" stopColor={c2} />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="22" height="22" rx="6" fill={`url(#${id}-bar)`} />
        <rect x="6" y="7.5" width="12" height="9" rx="1.5" fill="#fff" opacity="0.92" />
        <rect x="6" y="7.5" width="12" height="2.4" rx="1.2" fill="#000" opacity="0.18" />
      </svg>
    );
  }
  if (lower === "cl" || lower === "bz" || lower === "ng" || lower === "wti" || lower === "brent" || row.asset_type === "energy") {
    const isGas = lower === "ng" || lower === "naturalgas";
    const c1 = isGas ? "#38BDF8" : "#0F766E";
    const c2 = isGas ? "#1D4ED8" : "#134E4A";
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden className="h-6 w-6 shrink-0 rounded-full">
        <defs>
          <linearGradient id={`${id}-oil`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={c1} />
            <stop offset="1" stopColor={c2} />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="22" height="22" rx="6" fill={`url(#${id}-oil)`} />
        <path d={isGas ? FLAME_PATH : OIL_PATH} fill="#fff" opacity="0.95" transform="scale(0.92) translate(1.1 1.1)" />
      </svg>
    );
  }

  // Equities and everything else: brand-color rounded mark with ticker letters.
  const color = BRAND_COLORS[ticker] ?? "#64748B";
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden className="h-6 w-6 shrink-0 rounded-full">
      <defs>
        <linearGradient id={`${id}-eq`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={color} />
          <stop offset="1" stopColor={shade(color, -45)} />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="22" height="22" rx="6" fill={`url(#${id}-eq)`} />
      <text x="12" y="15.5" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#fff">
        {ticker.slice(0, 2)}
      </text>
    </svg>
  );
}

function groupLabel(copy: Record<string, unknown>, group: string) {
  const value = copy[`group.${group}`];
  return typeof value === "string" ? value : group;
}

function fmtPrice(locale: Locale, row: GlobalMarketRow) {
  const value = row.price;
  if (row.asset_type === "forex") return value.toFixed(4);
  if (row.asset_type === "commodity") return `$${value.toLocaleString(locale, { maximumFractionDigits: 2 })}`;
  return `$${value.toLocaleString(locale, { maximumFractionDigits: 2 })}`;
}

export function GlobalMarketTerminal({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const copy = useMemo(() => getMessageNamespace(locale, "dashboard"), [locale]);
  const [data, setData] = useState<GlobalMarketSnapshot | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    const result = await getGlobalMarket(locale);
    setData(result);
    setLoading(false);
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale]);

  const groups = useMemo(() => {
    if (!data) return [] as { group: string; rows: GlobalMarketRow[] }[];
    return GROUP_ORDER.filter((group) => data.groups[group]?.length).map((group) => ({ group, rows: data.groups[group] }));
  }, [data]);

  const hasData = groups.some((item) => item.rows.length > 0);

  return (
    <section className="workbench">
      <div className="workbench-head">
        <div>
          <div className="text-eyebrow uppercase text-text-pg-muted">{copy.marketTerminal}</div>
          <h2 className="mt-1 font-semibold">{copy.crossMarketTape}</h2>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" disabled={loading} onClick={() => void load()} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-[11px] text-text-pg-muted disabled:opacity-50 rounded-lg"><RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />{zh ? "刷新" : "Refresh"}</button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] font-mono text-xs">
          <thead className="text-left text-[10px] uppercase text-text-pg-dim">
            <tr><th className="px-4 py-2 font-medium">{copy.ticker}</th><th className="px-3 py-2 text-right font-medium">{copy.last}</th><th className="px-3 py-2 text-right font-medium">%</th><th className="px-3 py-2 font-medium">{zh ? "类别" : "Group"}</th><th className="px-4 py-2 text-right font-medium">UTC</th></tr>
          </thead>
          <tbody>
            {groups.map(({ group, rows }) => (
              <GroupSection key={group} group={group} rows={rows} copy={copy} locale={locale} />
            ))}
          </tbody>
        </table>
        {!hasData ? <p className="p-4 text-sm text-text-pg-muted">{data?.unavailable ? copy.waitingFeed : copy.waitingFeed}</p> : null}
      </div>
    </section>
  );
}

function GroupSection({ group, rows, copy, locale }: { group: string; rows: GlobalMarketRow[]; copy: Record<string, unknown>; locale: Locale }) {
  return (
    <>
      <tr><td colSpan={5} className="bg-bg-panel-muted px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{groupLabel(copy, group)}</td></tr>
      {rows.map((row) => (
        <tr key={`${group}-${row.symbol}`} className="border-t border-border-pg/70 hover:bg-bg-panel-muted">
          <td className="px-4 py-3"><div className="flex items-center gap-2.5"><MarketLogo row={row} /><span className="font-semibold text-text-pg">{row.symbol}<span className={`ml-2 text-[9px] ${row.is_realtime ? "text-status-positive" : "text-status-warning"}`}>{row.is_realtime ? "LIVE" : "DLY"}</span></span></div></td>
          <td className="px-3 py-3 text-right text-text-pg">{fmtPrice(locale, row)}</td>
          <td className={`px-3 py-3 text-right ${row.change_24h != null && row.change_24h >= 0 ? "text-status-positive" : "text-status-negative"}`}>{row.change_24h != null ? `${row.change_24h >= 0 ? "+" : ""}${row.change_24h.toFixed(2)}` : "-"}</td>
          <td className="max-w-[150px] truncate px-3 py-3 text-text-pg-muted">{row.source || "-"}</td>
          <td className="px-4 py-3 text-right text-text-pg-dim">{row.timestamp ? new Date(row.timestamp).toISOString().slice(11, 19) : "-"}</td>
        </tr>
      ))}
    </>
  );
}