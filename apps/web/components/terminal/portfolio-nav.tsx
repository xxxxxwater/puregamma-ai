"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { getPortfolioSnapshot, type PortfolioSnapshot } from "@/lib/api";
import { SectionLabel } from "@/components/terminal/editorial";
import { SignalStatus } from "@/components/terminal/signal-status";
import { type Locale, withLocale } from "@/i18n/routing";

/** Portfolio exposure / NAV for the briefing. Real snapshot only. */
export function PortfolioNav({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [data, setData] = useState<PortfolioSnapshot | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPortfolioSnapshot(locale).then((payload) => { if (!cancelled) { setData(payload); setLoaded(true); } }).catch(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [locale]);

  const connected = Boolean(data?.connected);
  const stale = Boolean(data?.stale);
  const nav = data?.nav != null && data.nav >= 0 ? data.nav : null;
  const asOf = data?.data_as_of || null;
  const asOfLabel = asOf ? new Date(asOf).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }) : null;

  return (
    <div className="terminal-panel portfolio-nav" data-chrono-slice>
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>{zh ? "Portfolio / NAV" : "Portfolio / NAV"}</SectionLabel>
        <Link href={withLocale(locale, "/portfolio")} className="inline-flex items-center gap-1 text-[0.7rem] text-muted hover:text-foreground">{zh ? "详情" : "Details"}<ArrowUpRight className="h-3 w-3" aria-hidden /></Link>
      </div>
      <div className="mt-3 tabular-nums"><span className="nav-value">{nav == null ? "—" : "$" + nav.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></div>
      <div className="mt-1 text-[0.72rem] text-muted-2">
        {!loaded ? (zh ? "读取组合…" : "Loading portfolio…")
          : !connected ? (zh ? "尚未连接投资账户" : "No investment account connected")
          : stale ? (zh ? "数据过期 — 请同步账户" : "Stale — sync your account")
          : (zh ? "净值 (NAV)" : "Net asset value") + (asOfLabel ? ` · ${asOfLabel}` : "")}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {loaded && connected ? (stale ? <SignalStatus tone="warn" label="STALE" /> : <SignalStatus tone="good" label="FRESH" />) : <SignalStatus tone="idle" label="NONE" />}
      </div>
    </div>
  );
}