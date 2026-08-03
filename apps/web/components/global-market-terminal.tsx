"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Badge, ResearchCard } from "@/components/puregamma";
import { getMessageNamespace } from "@/lib/translations";
import { getGlobalMarket, type GlobalMarketRow, type GlobalMarketSnapshot } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const GROUP_ORDER = ["nasdaq_top", "metals", "forex", "energy"];

function groupLabel(copy: Record<string, unknown>, group: string) {
  const value = copy[`group.${group}`];
  return typeof value === "string" ? value : group;
}

function fmtPrice(locale: Locale, row: GlobalMarketRow) {
  const value = row.price;
  if (row.asset_type === "forex") return value.toFixed(4);
  if (row.asset_type === "commodity") return `$${value.toLocaleString(locale, { maximumFractionDigits: 2 })}`;
  return value >= 100 ? `$${value.toLocaleString(locale, { maximumFractionDigits: 2 })}` : `$${value.toLocaleString(locale, { maximumFractionDigits: 2 })}`;
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
          <Badge tone={data?.status === "HEALTHY" ? "emerald" : "amber"}>{data?.status ?? "-"}</Badge>
          <button type="button" disabled={loading} onClick={() => void load()} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-[11px] text-text-pg-muted disabled:opacity-50"><RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />{zh ? "刷新" : "Refresh"}</button>
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
          <td className="px-4 py-3 font-semibold text-text-pg">{row.symbol}<span className={`ml-2 text-[9px] ${row.is_realtime ? "text-status-positive" : "text-status-warning"}`}>{row.is_realtime ? "LIVE" : "DLY"}</span></td>
          <td className="px-3 py-3 text-right text-text-pg">{fmtPrice(locale, row)}</td>
          <td className={`px-3 py-3 text-right ${row.change_24h != null && row.change_24h >= 0 ? "text-status-positive" : "text-status-negative"}`}>{row.change_24h != null ? `${row.change_24h >= 0 ? "+" : ""}${row.change_24h.toFixed(2)}` : "-"}</td>
          <td className="max-w-[150px] truncate px-3 py-3 text-text-pg-muted">{row.source || "-"}</td>
          <td className="px-4 py-3 text-right text-text-pg-dim">{row.timestamp ? new Date(row.timestamp).toISOString().slice(11, 19) : "-"}</td>
        </tr>
      ))}
    </>
  );
}
