"use client";

import { useMemo } from "react";
import { formatClockTime, formatUtcTime, useClockNow, MARKET_STATUS_WORD, type MarketStatus } from "@/lib/chrono";



/** The system presence: live status, local + UTC time, data as-of, and the
 * live-asset count. Honest states only; hydration-safe. */
export function MarketPresence({ locale, status = "waiting", dataAsOf, liveLabel }: {
  locale: "en" | "zh";
  status?: MarketStatus;
  dataAsOf?: string | null;
  liveLabel?: string | null;
}) {
  const zh = locale === "zh";
  const now = useClockNow(1000);
  const word = MARKET_STATUS_WORD[status];
  const asOf = useMemo(() => {
    if (!dataAsOf) return null;
    const d = new Date(dataAsOf);
    return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" });
  }, [dataAsOf, zh]);
  const live = status === "live";
  const canShowLiveLabel = (status === "live" || status === "delayed") && Boolean(liveLabel);
  const dot = live ? "status-dot-live" : (status === "stale" || status === "waiting" ? "status-dot-warn" : "status-dot-idle");
  return (
    <div className="intelligence-clock flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.66rem] font-medium uppercase tracking-[0.16em] text-muted-2">
      <span className={"status-dot " + dot} aria-hidden />
      <span className={"status-word " + (live ? "text-accent" : "text-muted-2")}>{zh ? word.zh : word.en}</span>
      <span aria-hidden className="h-px w-5 bg-border-pg-strong" />
      <span className="clock-time tabular-nums">{formatClockTime(now, zh ? "zh-CN" : "en-US", true)}</span>
      <span>UTC {formatUtcTime(now, true)}</span>
      {asOf ? <span>{zh ? "更新于 " : "data as of "}{asOf}</span> : null}
      {canShowLiveLabel ? <span className="text-muted-2">{liveLabel}</span> : null}
    </div>
  );
}
