"use client";

import { useEffect, useMemo, useState } from "react";
import { Coins, Flame, Globe, RefreshCw } from "lucide-react";
import { ResearchCard } from "@/components/puregamma";
import { getMessageNamespace } from "@/lib/translations";
import { getGlobalMarket, type GlobalMarketRow, type GlobalMarketSnapshot } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const GROUP_ORDER = ["nasdaq_top", "metals", "forex", "energy"];

// Company domain map for equity tickers (delayed yahoo quotes). Icons load
// from Google's favicon service; unknown tickers fall back to a letter badge.
const COMPANY_DOMAINS: Record<string, string> = {
  NVDA: "nvidia.com",
  MSFT: "microsoft.com",
  AAPL: "apple.com",
  PLTR: "palantir.com",
  AMZN: "amazon.com",
  TSLA: "tesla.com",
  META: "meta.com",
  GOOGL: "google.com",
  GOOG: "google.com",
  NFLX: "netflix.com",
  AMD: "amd.com",
  INTC: "intel.com",
  ORCL: "oracle.com",
  CRM: "salesforce.com",
  AVGO: "broadcom.com",
  MU: "micron.com",
  SMCI: "supermicro.com",
  COIN: "coinbase.com",
  SHOP: "shopify.com",
  UBER: "uber.com",
  SNAP: "snap.com",
  PINS: "pinterest.com",
  SQ: "block.xyz",
  PYPL: "paypal.com",
  DIS: "disney.com",
  JPM: "jpmorganchase.com",
  BAC: "bankofamerica.com",
  XOM: "exxonmobil.com",
  CVX: "chevron.com",
  JNJ: "jnj.com",
  PFE: "pfizer.com",
  UNH: "unitedhealthgroup.com",
  WMT: "walmart.com",
  PG: "pg.com",
  KO: "coca-colacompany.com",
  PEP: "pepsi.com",
  MCD: "mcdonalds.com",
  NKE: "nike.com",
  BA: "boeing.com",
  CAT: "caterpillar.com",
  GE: "ge.com",
  F: "ford.com",
  GM: "gm.com",
};

function normalizeTicker(symbol: string): string {
  return symbol.replace(/DLY$/, "").replace(/=X$/, "").replace(/=F$/, "");
}

function letterBadge(ticker: string, tone: "accent" | "gold" | "sky" | "amber") {
  const bg = { accent: "bg-status-positive/15 text-status-positive", gold: "bg-[#f59e0b]/15 text-[#f59e0b]", sky: "bg-[#60a5fa]/15 text-[#60a5fa]", amber: "bg-status-warning/20 text-status-warning" }[tone];
  return <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-bold ${bg}`}>{ticker.charAt(0)}</span>;
}

function MarketIcon({ row }: { row: GlobalMarketRow }) {
  const [failed, setFailed] = useState(false);
  const ticker = normalizeTicker(row.symbol);
  const domain = COMPANY_DOMAINS[ticker.toUpperCase()];
  if (domain && !failed) {
    return <img
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
      alt={ticker}
      width={24}
      height={24}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-6 w-6 shrink-0 rounded-full object-cover"
    />;
  }
  const lower = ticker.toLowerCase();
  if (lower.includes("eur") || lower.includes("usd") || lower.includes("jpy") || lower.includes("gbp") || lower.includes("aud") || row.asset_type === "forex") {
    return <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#60a5fa]/15 text-[#60a5fa]"><Globe className="h-3.5 w-3.5" /></span>;
  }
  if (row.asset_type === "commodity" || lower.includes("gold") || lower.includes("silver") || lower === "gc" || lower === "si") {
    return <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#f59e0b]/15 text-[#f59e0b]"><Coins className="h-3.5 w-3.5" /></span>;
  }
  if (lower === "cl" || lower === "bz" || lower === "ng" || lower === "wti" || lower === "brent") {
    return <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-status-warning/20 text-status-warning"><Flame className="h-3.5 w-3.5" /></span>;
  }
  return letterBadge(ticker, "accent");
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
    <ResearchCard className="overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-border-pg px-4 py-3">
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
          <thead className="bg-bg-panel-muted text-left text-[10px] uppercase text-text-pg-dim">
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
    </ResearchCard>
  );
}

function GroupSection({ group, rows, copy, locale }: { group: string; rows: GlobalMarketRow[]; copy: Record<string, unknown>; locale: Locale }) {
  return (
    <>
      <tr><td colSpan={5} className="bg-bg-panel-muted px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{groupLabel(copy, group)}</td></tr>
      {rows.map((row) => (
        <tr key={`${group}-${row.symbol}`} className="border-t border-border-pg/70 hover:bg-bg-panel-muted">
          <td className="px-4 py-3"><div className="flex items-center gap-2.5"><MarketIcon row={row} /><span className="font-semibold text-text-pg">{row.symbol}<span className={`ml-2 text-[9px] ${row.is_realtime ? "text-status-positive" : "text-status-warning"}`}>{row.is_realtime ? "LIVE" : "DLY"}</span></span></div></td>
          <td className="px-3 py-3 text-right text-text-pg">{fmtPrice(locale, row)}</td>
          <td className={`px-3 py-3 text-right ${row.change_24h != null && row.change_24h >= 0 ? "text-status-positive" : "text-status-negative"}`}>{row.change_24h != null ? `${row.change_24h >= 0 ? "+" : ""}${row.change_24h.toFixed(2)}` : "-"}</td>
          <td className="max-w-[150px] truncate px-3 py-3 text-text-pg-muted">{row.source || "-"}</td>
          <td className="px-4 py-3 text-right text-text-pg-dim">{row.timestamp ? new Date(row.timestamp).toISOString().slice(11, 19) : "-"}</td>
        </tr>
      ))}
    </>
  );
}
