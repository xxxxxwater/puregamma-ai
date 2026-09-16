"use client";

import { useCallback, useEffect, useState } from "react";
import { NavHistoryChart } from "@/components/charts";
import { ResearchCard } from "@/components/puregamma";
import { PortfolioConsole } from "@/components/portfolio-console";
import { API_URL } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

type Account = Record<string, string | undefined>;
type Balance = { asset: string; wallet_balance?: string; btc_equivalent?: string; usd_equivalent?: string; borrowed?: string; interest?: string };
type Position = { product: string; symbol: string; side: string; quantity?: string; entry_price?: string; mark_price?: string; notional_usd?: string; unrealized_pnl?: string; protection_status?: string };
type Order = { product: string; kind: string; symbol: string; order_id: string; side: string; order_type: string; status: string; quantity?: string; executed_quantity?: string; price?: string; trigger_price?: string; reduce_only: boolean; close_position: boolean };
type Snapshot = { source: string; captured_at: string; age_seconds: number; stale: boolean; account: Account; balances: Balance[]; positions: Position[]; orders: Order[] | null; orders_age_seconds: number | null; orders_stale: boolean };
type History = { points: { captured_at: string; equity_usd: string; equity_btc?: string }[] };
const n = (v: string | undefined | null) => v === undefined || v === null || v === "" || !Number.isFinite(Number(v)) ? null : Number(v);
const fmt = (v: string | undefined | null, locale: Locale, digits = 2) => n(v) === null ? "--" : n(v)!.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const usd = (v: string | undefined | null, locale: Locale) => n(v) === null ? "--" : n(v)!.toLocaleString(locale, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
async function read<T>(path: string): Promise<{ status: number; data: T | null }> {
  try {
    const r = await fetch(`${API_URL}/portfolio/private-pm/${path}`, { credentials: "include", cache: "no-store", signal: AbortSignal.timeout(7000) });
    return { status: r.status, data: r.ok ? await r.json() as T : null };
  } catch { return { status: 0, data: null }; }
}

export function PrivatePMPortfolio({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [access, setAccess] = useState<"checking" | "allowed" | "other" | "error">("checking");
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [history, setHistory] = useState<History["points"]>([]);
  const [range, setRange] = useState<"1D" | "1W" | "1M" | "ALL">("1M");
  const [unit, setUnit] = useState<"USD" | "BTC">("USD");
  const refresh = useCallback(async () => {
    const r = await read<Snapshot>("snapshot");
    // Fail closed: never pass off a stale previous figure as current.
    setSnap(r.status === 200 && r.data?.source === "binance_pm_classic" ? r.data : null);
    if (r.status === 403) setAccess("error");
  }, []);
  useEffect(() => {
    let active = true;
    void read<{ authorized: boolean }>("access").then(r => {
      if (!active) return;
      setAccess(r.status === 200 && r.data?.authorized ? "allowed" : r.status === 403 ? "other" : "error");
    });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (access !== "allowed") return;
    void refresh();
    const refreshHistory = () => void read<History>("history").then(r => { if (r.data?.points) setHistory(r.data.points); });
    refreshHistory();
    const tick = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 15000);
    const hist = window.setInterval(() => { if (document.visibilityState === "visible") refreshHistory(); }, 60000);
    return () => { clearInterval(tick); clearInterval(hist); };
  }, [access, refresh]);
  if (access === "other") return <PortfolioConsole locale={locale} />;
  if (access === "checking" || access === "error") return <div role="status" className="rounded-xl border border-border-pg p-6 text-sm text-text-pg-muted">{access === "checking" ? (zh ? "正在验证账户权限…" : "Checking permissions…") : (zh ? "无法验证私有账户权限；不会显示账户数据。" : "Unable to verify private account permissions.")}</div>;
  const a = snap?.account;
  const realBtc = n(a?.btc_wallet_quantity);
  const btcPrice = n(a?.btc_usdt_mark);
  const collateralUsd = realBtc === null || btcPrice === null ? null : String(realBtc * btcPrice);
  const p = snap?.positions || [];
  const pnl = p.length && p.every(x => n(x.unrealized_pnl) !== null) ? String(p.reduce((s, x) => s + (n(x.unrealized_pnl) || 0), 0)) : undefined;
  const balances = snap?.balances.filter(b => n(b.wallet_balance) !== 0) || [];
  const windows = { "1D": 86400000, "1W": 7 * 86400000, "1M": 30 * 86400000, ALL: Infinity };
  const curve = history.filter(x => Date.parse(x.captured_at) >= Date.now() - windows[range])
    .map(x => ({ date: x.captured_at, nav: n(unit === "USD" ? x.equity_usd : x.equity_btc) }))
    .filter((x): x is { date: string; nav: number } => x.nav !== null);
  const metrics: [string, string][] = [
    [zh ? "BTC 实际持币数量" : "Actual BTC wallet", `${fmt(a?.btc_wallet_quantity, locale, 8)} BTC`],
    [zh ? "BTC 抵押市值（未扣折扣）" : "BTC collateral market value", usd(collateralUsd, locale)],
    [zh ? "官方调整后权益" : "Official actual equity", usd(a?.actual_equity_usd, locale)],
    [zh ? "可用资金" : "Available balance", usd(a?.available_usd, locale)],
    [zh ? "可用资金 BTC 等值" : "Available BTC equivalent", `${fmt(a?.available_btc_equivalent, locale, 8)} BTC`],
    [zh ? "持仓未实现盈亏（衍生汇总）" : "Position unrealized PnL (derived)", usd(pnl, locale)],
    [zh ? "初始保证金" : "Initial margin", usd(a?.initial_margin_usd, locale)],
    [zh ? "维持保证金" : "Maintenance margin", usd(a?.maintenance_margin_usd, locale)],
  ];
  return <div className="space-y-5">
    <ResearchCard className="overflow-hidden p-0"><div className="p-5">
      <div className="flex items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "组合净值 NAV · Binance 统一 PM" : "Portfolio NAV · Binance PM"}</p><p className="mt-1 text-xs text-text-pg-muted">{zh ? "只读 · BTC 抵押 · 不启用交易" : "Read-only · BTC collateral · Trading disabled"}</p></div><button className="rounded border border-border-pg px-3 py-2 text-xs" onClick={() => void refresh()} type="button">{zh ? "刷新" : "Refresh"}</button></div>
      {!snap ? <p role="status" className="mt-5 text-text-pg-muted">{zh ? "真实账户快照不可用，不展示虚构金额。" : "Live PM snapshot unavailable; no fabricated values."}</p> : <>
        {snap.stale && <p role="alert" className="mt-3 text-status-negative">{zh ? "警告：账户数据已过期" : "Warning: account data is stale"}</p>}
        <p className="mt-5 text-xs text-text-pg-muted">{zh ? "官方账户净值（USD）" : "Official NAV (USD)"}</p><p className="mt-1 text-4xl font-semibold">{usd(a?.account_equity_usd, locale)}</p><p className="mt-2 text-sm text-text-pg-muted">≈ {fmt(a?.equity_btc_equivalent, locale, 8)} BTC {zh ? "净值等值（不是实际持币量）" : "NAV equivalent, not BTC wallet quantity"}</p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-lg border border-border-pg p-3"><p className="text-xs text-text-pg-muted">{label}</p><p className="mt-1 text-base font-semibold break-all">{value}</p></div>)}</div>
        <p className="mt-3 text-xs text-text-pg-muted">{zh ? "抵押市值、账户净值、可用保证金不同；负余额保留负号。" : "Collateral market value, NAV and available margin are distinct. Negative balances retain their sign."}</p>
        <div className="mt-5 flex flex-wrap gap-2">{(["USD", "BTC"] as const).map(v => <button className="rounded border border-border-pg px-3 py-1 text-xs" key={v} onClick={() => setUnit(v)} type="button" aria-pressed={unit === v}>{v}</button>)}{(["1D", "1W", "1M", "ALL"] as const).map(v => <button className="rounded border border-border-pg px-3 py-1 text-xs" key={v} onClick={() => setRange(v)} type="button" aria-pressed={range === v}>{v}</button>)}</div><p className="mt-2 text-xs text-text-pg-muted">{zh ? "仅真实历史快照；不会补造历史净值" : "Real historical snapshots only; no backfilled estimates"}</p>
      </>}
    </div>{snap && (curve.length > 1 ? <NavHistoryChart data={curve} /> : <div className="grid h-48 place-items-center border-t border-border-pg text-xs text-text-pg-muted">{zh ? "真实快照不足，曲线尚未形成" : "Not enough real snapshots for a chart"}</div>)}</ResearchCard>
    {snap && <>
      <ResearchCard className="p-5"><h2 className="font-semibold">{zh ? "风险及账户状态" : "Account risk"}</h2><p className="mt-2 text-xs text-text-pg-muted">{zh ? "账户状态" : "Status"}: {a?.account_status} · uniMMR: {a?.uni_mmr} · {zh ? "名义敞口" : "Gross exposure"}: {usd(a?.gross_notional_usd, locale)} · {zh ? "参考价格" : "BTC reference"}: {usd(a?.btc_usdt_mark,locale)} · {new Date(snap.captured_at).toLocaleString(locale)} · {snap.age_seconds}s</p></ResearchCard>
      <ResearchCard className="overflow-hidden p-0"><h2 className="border-b border-border-pg p-5 font-semibold">{zh ? "资产币种" : "Assets"} · {balances.length}</h2><div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead><tr>{["Asset","Wallet qty","BTC equiv.","USD equiv.","Borrowed","Interest"].map(v => <th className="p-3" key={v}>{v}</th>)}</tr></thead><tbody>{balances.map(b => <tr className="border-t border-border-pg" key={b.asset}><td className="p-3 font-semibold">{b.asset}</td><td className="p-3">{fmt(b.wallet_balance,locale,8)}</td><td className="p-3">{fmt(b.btc_equivalent,locale,8)}</td><td className="p-3">{usd(b.usd_equivalent,locale)}</td><td className="p-3">{fmt(b.borrowed,locale,8)}</td><td className="p-3">{fmt(b.interest,locale,8)}</td></tr>)}</tbody></table></div></ResearchCard>
      <ResearchCard className="overflow-hidden p-0"><h2 className="border-b border-border-pg p-5 font-semibold">{zh ? "实时仓位" : "Positions"} · {p.length}</h2><div className="overflow-x-auto"><table className="w-full min-w-[800px] text-left text-xs"><thead><tr>{["Symbol","Side","Quantity","Entry","Mark","Notional USD","PnL USD","Protection"].map(v => <th className="p-3" key={v}>{v}</th>)}</tr></thead><tbody>{p.map(x => <tr className="border-t border-border-pg" key={`${x.product}:${x.symbol}:${x.side}`}><td className="p-3">{x.symbol}</td><td className="p-3">{x.side}</td><td className="p-3">{fmt(x.quantity,locale,6)}</td><td className="p-3">{usd(x.entry_price,locale)}</td><td className="p-3">{usd(x.mark_price,locale)}</td><td className="p-3">{usd(x.notional_usd,locale)}</td><td className="p-3">{usd(x.unrealized_pnl,locale)}</td><td className="p-3">{x.protection_status ?? "unknown"}</td></tr>)}</tbody></table></div></ResearchCard>
      <ResearchCard className="overflow-hidden p-0"><h2 className="border-b border-border-pg p-5 font-semibold">{zh ? "当前订单" : "Open orders"} · {snap.orders?.length ?? "--"}</h2>{snap.orders_stale && <p role="alert" className="p-3 text-xs text-status-negative">{zh ? "挂单数据未实时同步，以下不展示旧订单" : "Order data is stale; old orders are not displayed"}</p>}{snap.orders && <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-xs"><thead><tr>{["ID","Symbol","Side","Type","Qty","Filled","Price","Trigger","Status"].map(v => <th className="p-3" key={v}>{v}</th>)}</tr></thead><tbody>{snap.orders.map(x => <tr className="border-t border-border-pg" key={`${x.product}:${x.kind}:${x.order_id}`}><td className="p-3">{x.order_id}</td><td className="p-3">{x.symbol}</td><td className="p-3">{x.side}</td><td className="p-3">{x.order_type}</td><td className="p-3">{fmt(x.quantity,locale,6)}</td><td className="p-3">{fmt(x.executed_quantity,locale,6)}</td><td className="p-3">{usd(x.price,locale)}</td><td className="p-3">{usd(x.trigger_price,locale)}</td><td className="p-3">{x.status}</td></tr>)}</tbody></table></div>}</ResearchCard>
    </>}
  </div>;
}
