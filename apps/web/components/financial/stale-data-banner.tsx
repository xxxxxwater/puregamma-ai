"use client";

import { CircleAlert, CircleCheck, RefreshCw } from "lucide-react";

/**
 * Data-freshness banner for Portfolio / NAV / Trading surfaces.
 * Stale state is prominent on purpose — never a tiny corner note.
 * Financial surfaces only; no animation.
 */
export function StaleDataBanner({ stale, updatedAt, locale, onRefresh, reconciliation }: {
  stale: boolean;
  updatedAt?: string | null;
  locale: "en" | "zh";
  onRefresh?: () => void;
  reconciliation?: string | null;
}) {
  const zh = locale === "zh";
  const timestamp = updatedAt ? new Date(updatedAt).toLocaleString(locale) : null;

  if (!stale) {
    if (!timestamp) return null;
    return (
      <p className="flex items-center gap-1.5 text-xs text-text-pg-dim">
        <CircleCheck className="h-3.5 w-3.5 shrink-0 text-status-positive" aria-hidden />
        {zh ? "数据更新于" : "Data updated"} {timestamp}
        {reconciliation === "pending" || reconciliation === "mismatch" ? <span className="text-status-warning"> · {zh ? "对账待复核" : "reconciliation needs review"}</span> : null}
      </p>
    );
  }

  return (
    <div role="alert" className="flex flex-wrap items-start gap-3 border border-status-warning bg-bg-panel-muted p-3">
      <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-status-warning">{zh ? "数据已过期（stale）" : "Data is stale"}</p>
        <p className="mt-1 text-xs leading-5 text-text-pg-muted">
          {zh
            ? "显示中的 NAV / 风险数值可能未反映最新市场价格。请同步账户后再做判断；过期状态下的任何交易操作都应暂停。"
            : "NAV and risk figures shown may not reflect the latest market prices. Sync your account before making judgments; hold off on any trading action while data is stale."}
        </p>
        {timestamp ? <p className="mt-1 text-xs text-text-pg-dim">{zh ? "最后更新" : "Last updated"}: {timestamp}</p> : null}
      </div>
      {onRefresh ? (
        <button type="button" onClick={onRefresh} className="inline-flex h-8 items-center gap-1.5 border border-border-pg px-2.5 text-xs text-text-pg hover:border-border-pg-strong rounded-lg">
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          {zh ? "同步" : "Sync"}
        </button>
      ) : null}
    </div>
  );
}
