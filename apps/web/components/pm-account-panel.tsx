"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ResearchCard } from "@/components/puregamma";
import type { PmAccountView, PmNavHistory, PmNavPoint } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

/**
 * Private Binance Portfolio Margin account, collected read-only by riskbot.
 *
 * The hero and the curve read the SAME field — the exchange's adjusted equity
 * (actualEquity) = market value minus liabilities — so the last point of the
 * curve always equals the hero figure. The two other figures are shown next to
 * it rather than being conflated with it:
 *
 *   hero / curve      official actualEquity      = 市值 − 负债（币安口径）
 *   sub-line (derived) 逐币种余额实测的 市值 − 负债（与官方差 <0.2%，估值方法差异）
 *   sub-line (margin)  official accountEquity    = 保证金/uniMMR 口径，约低 5%
 *
 * accountEquity must never be the headline: it is the stricter margin basis, not
 * what the account is worth. The three cells below the hero carry the facts the
 * hero does not: the coin actually held (official totalWalletBalance), that same
 * accountEquity expressed in BTC, and the liabilities.
 *
 * Never show one of these numbers under another's label, and never call a
 * derived figure "official".
 *
 * The NAV curve plots real snapshots only; with fewer than two points in a range
 * it says so instead of interpolating a line.
 */

type Currency = "USD" | "BTC";
type RangeKey = "1H" | "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL";

const RANGES: Array<{ key: RangeKey; seconds: number }> = [
  { key: "1H", seconds: 3_600 },
  { key: "1D", seconds: 86_400 },
  { key: "1W", seconds: 7 * 86_400 },
  { key: "1M", seconds: 30 * 86_400 },
  { key: "3M", seconds: 90 * 86_400 },
  { key: "1Y", seconds: 365 * 86_400 },
  { key: "ALL", seconds: Number.POSITIVE_INFINITY }
];

// Server values are Decimal strings; the account bag also carries booleans, so
// every formatter accepts `unknown` and narrows instead of casting.
function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fmtUsd(value: unknown, locale: Locale, digits = 2): string {
  const parsed = num(value);
  if (parsed === null) return "--";
  return parsed.toLocaleString(locale, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtBtc(value: unknown, locale: Locale, digits = 6): string {
  const parsed = num(value);
  if (parsed === null) return "--";
  return `${parsed.toLocaleString(locale, { minimumFractionDigits: 0, maximumFractionDigits: digits })} BTC`;
}

function fmtBare(value: unknown, locale: Locale, digits = 2): string {
  const parsed = num(value);
  if (parsed === null) return "--";
  return parsed.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function compactUsd(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function compactBtc(value: number): string {
  return value.toFixed(value >= 100 ? 0 : 2);
}

function signed(value: number, formatter: (input: number) => string): string {
  return `${value >= 0 ? "+" : "−"}${formatter(Math.abs(value))}`;
}

// ---------------------------------------------------------------- NAV chart

type ChartPoint = { t: number; netUsd: number | null; netBtc: number | null };

function NavTooltip({ active, payload, locale, currency }: {
  active?: boolean;
  payload?: Array<{ payload?: ChartPoint }>;
  locale?: Locale;
  currency?: Currency;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const loc = (locale ?? "en") as Locale;
  return (
    <div className="border border-border-pg bg-bg-panel px-3 py-2 text-xs rounded-lg">
      <div className="mb-1 text-text-pg-muted">{new Date(point.t * 1000).toLocaleString(loc)}</div>
      <div className={`tabular-nums ${currency === "USD" ? "font-medium text-text-pg" : "text-text-pg-muted"}`}>
        {loc === "zh" ? "权益" : "Equity"}: {fmtUsd(point.netUsd, loc)}
      </div>
      <div className={`tabular-nums ${currency === "BTC" ? "font-medium text-text-pg" : "text-text-pg-muted"}`}>
        {loc === "zh" ? "权益 (BTC)" : "Equity in BTC"}: {fmtBtc(point.netBtc, loc, 8)}
      </div>
    </div>
  );
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "positive" | "negative" }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</dt>
      <dd className={`mt-1 truncate text-lg font-semibold tabular-nums ${tone === "positive" ? "text-status-positive" : tone === "negative" ? "text-status-negative" : "text-text-pg"}`}>{value}</dd>
      {hint ? <p className="mt-0.5 truncate text-[10px] text-text-pg-dim">{hint}</p> : null}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-bg-panel px-3 py-2.5">
      <dt className="text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums text-text-pg">{value}</dd>
      {hint ? <p className="mt-0.5 text-[10px] leading-4 text-text-pg-dim">{hint}</p> : null}
    </div>
  );
}

/** One of the three BTC figures, always carrying its own definition. */
function BtcCell({ title, value, source, accent }: { title: string; value: string; source: string; accent?: boolean }) {
  return (
    <div className="bg-bg-panel px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-text-pg-dim">{title}</div>
      <div className={`mt-0.5 text-sm tabular-nums ${accent ? "font-semibold text-text-pg" : "font-medium text-text-pg"}`}>{value}</div>
      <div className="mt-0.5 text-[10px] leading-4 text-text-pg-dim">{source}</div>
    </div>
  );
}

const CHANGE_LABEL: Record<string, { zh: string; en: string; tone: string }> = {
  ENTRY: { zh: "开仓", en: "Open", tone: "text-status-positive" },
  INCREASE: { zh: "加仓", en: "Increase", tone: "text-status-positive" },
  REDUCE: { zh: "减仓", en: "Reduce", tone: "text-status-negative" },
  EXIT: { zh: "平仓", en: "Close", tone: "text-status-negative" },
  FLIP: { zh: "翻向", en: "Flip", tone: "text-status-warning" }
};

export function PmAccountPanel({ view, history, loading, locale, onRefresh }: {
  view: PmAccountView | null;
  history: PmNavHistory | null;
  loading: boolean;
  locale: Locale;
  onRefresh?: () => void;
}) {
  const zh = locale === "zh";
  const [currency, setCurrency] = useState<Currency>("USD");
  const [range, setRange] = useState<RangeKey>("1D");
  const [nowTick, setNowTick] = useState(() => Date.now());

  // The page re-fetches every 60s; this keeps the LIVE / STALE indicator honest
  // between polls instead of freezing on a stale badge.
  useEffect(() => {
    const timer = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  const points = history?.points ?? [];
  // The curve MUST measure the same thing as the hero. It plots the exchange's
  // adjusted equity (actualEquity), i.e. market value minus liabilities - the
  // same definition as the hero figure - rather than accountEquity, which is the
  // stricter margin basis and about 5% lower.
  const allPoints = useMemo<ChartPoint[]>(() => points.map((point: PmNavPoint) => {
    const netUsd = num(point.adjusted_equity_usd);
    const price = num(point.btc_price_usd);
    return {
      t: point.t,
      netUsd,
      netBtc: netUsd !== null && price && price > 0 ? netUsd / price : null
    };
  }), [points]);

  const series = useMemo(() => {
    const seconds = RANGES.find((item) => item.key === range)?.seconds ?? Number.POSITIVE_INFINITY;
    if (!Number.isFinite(seconds) || !allPoints.length) return allPoints;
    const cutoff = allPoints[allPoints.length - 1].t - seconds;
    return allPoints.filter((point) => point.t >= cutoff);
  }, [allPoints, range]);

  const valueOf = (point: ChartPoint) => (currency === "USD" ? point.netUsd : point.netBtc);
  const usable = series.filter((point) => valueOf(point) !== null);
  const first = usable.length ? valueOf(usable[0]) : null;
  const last = usable.length ? valueOf(usable[usable.length - 1]) : null;
  const delta = first !== null && last !== null ? last - first : null;
  const deltaPct = delta !== null && first ? (delta / first) * 100 : null;
  const rising = (delta ?? 0) >= 0;

  const accent = rising ? "var(--positive)" : "var(--negative)";
  const gradientId = `pm-nav-${currency.toLowerCase()}`;

  const yValues = usable.map(valueOf).filter((value): value is number => value !== null);
  let yDomain: [number, number] | undefined;
  if (yValues.length > 1) {
    const min = Math.min(...yValues);
    const max = Math.max(...yValues);
    const pad = (max - min) * 0.08 || Math.abs(max) * 0.001 || 1;
    yDomain = [min - pad, max + pad];
  }

  const ageSeconds = useMemo(() => {
    const stamp = view?.generated_at ?? view?.data_as_of;
    if (!stamp) return view?.age_seconds ?? null;
    const parsed = Date.parse(stamp);
    return Number.isFinite(parsed) ? Math.max(0, (nowTick - parsed) / 1000) : (view?.age_seconds ?? null);
  }, [view?.generated_at, view?.data_as_of, view?.age_seconds, nowTick]);
  const staleAfter = view?.stale_after_seconds ?? 180;
  const live = ageSeconds !== null && ageSeconds <= staleAfter;

  if (loading && !view) {
    return <ResearchCard><div className="flex items-center gap-2 p-5 text-sm text-text-pg-muted"><Loader2 className="h-4 w-4 animate-spin" />{zh ? "正在读取只读账户数据…" : "Loading read-only account data…"}</div></ResearchCard>;
  }
  // A caller who is not one of the authorized accounts gets no UI at all.
  if (view?.reason === "forbidden") return null;
  if (!view || !view.available) {
    const reason = view?.reason;
    return <ResearchCard><div className="p-5 text-sm text-text-pg-muted">
      {zh ? `只读账户数据暂不可用${reason ? `（${reason}）` : ""}。此处不会显示任何估算或占位数值。` : `Read-only account data is unavailable${reason ? ` (${reason})` : ""}. No estimates or placeholder figures are shown.`}
    </div></ResearchCard>;
  }

  const account = view.account ?? {};
  const btc = view.btc ?? {};
  const exposure = view.exposure ?? {};
  const balances = view.balances ?? [];
  const positions = view.positions ?? [];
  const positionHistory = view.positions_history ?? [];
  const historyMeta = view.positions_history_meta ?? {};

  const equityUsd = num(account.account_equity_usd);
  const equityBtc = num(account.equity_btc_equivalent);
  const adjustedUsd = num(account.adjusted_equity_usd);
  const btcPrice = num(btc.price_usd);
  const walletBtc = num(btc.quantity);
  const availableUsd = num(account.total_available_balance_usd);
  const availableBtc = num(account.available_btc_equivalent);

  // 市值 − 负债：the user-facing definition of what the account is worth, kept
  // separate from the exchange's stricter accountEquity.
  const liabilityUsd = balances.reduce((total, row) => total + (row.is_liability ? Math.abs(num(row.value_usd) ?? 0) : 0), 0);
  const assetUsd = balances.reduce((total, row) => total + (row.is_liability ? 0 : (num(row.value_usd) ?? 0)), 0);
  const netWorthUsd = assetUsd - liabilityUsd;
  const netWorthBtc = btcPrice && btcPrice > 0 ? netWorthUsd / btcPrice : null;

  const upnlSum = balances.reduce((total, row) => total + (num(row.unrealized_pnl) ?? 0), 0);
  const upnlValue = num(account.total_unrealized_pnl_usd) ?? upnlSum;

  // Hero AND curve read the SAME field: the exchange's adjusted equity
  // (actualEquity), i.e. market value minus liabilities. They must not diverge -
  // an earlier version showed a per-asset derived figure in the hero and
  // accountEquity in the curve, and the two disagreed by design.
  //
  // accountEquity is a DIFFERENT (stricter) figure Binance uses for margin and
  // uniMMR, roughly 5% lower, so it is shown separately and never used as the
  // headline.
  const adjustedBtc = adjustedUsd !== null && btcPrice && btcPrice > 0 ? adjustedUsd / btcPrice : null;
  const heroValue = currency === "USD" ? adjustedUsd : adjustedBtc;
  const heroText = currency === "USD" ? fmtUsd(heroValue, locale) : fmtBtc(heroValue, locale, 8);
  const heroLabel = zh ? "账户权益 · Equity (market value − liabilities)" : "Equity · market value − liabilities";
  const heroSub = currency === "USD"
    ? (zh ? `市值 − 负债 实测 ${fmtUsd(netWorthUsd, locale)} · 官方 accountEquity（保证金口径）${fmtUsd(equityUsd, locale)}` : `derived market value − liabilities ${fmtUsd(netWorthUsd, locale)} · official accountEquity (margin basis) ${fmtUsd(equityUsd, locale)}`)
    : (zh ? `市值 − 负债 实测 ${fmtBtc(netWorthBtc, locale, 8)} · 官方 accountEquity（保证金口径）${fmtBtc(equityBtc, locale, 8)}` : `derived market value − liabilities ${fmtBtc(netWorthBtc, locale, 8)} · official accountEquity (margin basis) ${fmtBtc(equityBtc, locale, 8)}`);

  return <>
    <ResearchCard className="overflow-hidden p-0">
      {/* ------------------------------------------------ hero */}
      <div className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="inline-flex items-center gap-1.5 border border-border-pg bg-bg-panel-muted px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-text-pg-muted rounded-lg">
            Portfolio Margin
          </span>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide">
              <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-status-positive" : "bg-status-warning"}`} aria-hidden />
              <span className={live ? "text-status-positive" : "text-status-warning"}>{live ? "LIVE" : "STALE"}</span>
            </span>
            <span className="border border-border-pg px-2 py-1 text-[10px] text-text-pg-muted rounded-lg">READ ONLY</span>
            {onRefresh ? (
              <button type="button" onClick={onRefresh} className="grid h-6 w-6 place-items-center border border-border-pg text-text-pg-muted hover:text-text-pg rounded-lg" title={zh ? "刷新" : "Refresh"}>
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              </button>
            ) : null}
          </div>
        </div>

        <p className="mt-1 text-xs text-text-pg-muted">{heroLabel}</p>
        <p className={`mt-1 text-4xl font-semibold tracking-normal tabular-nums sm:text-5xl ${rising ? "text-status-positive" : "text-status-negative"}`}>{heroText}</p>
        {heroSub ? <p className="mt-1 text-xs text-text-pg-muted tabular-nums">{heroSub}</p> : null}

        {/* The three BTC figures, each with the field it comes from. */}
        <div className="mt-4 grid gap-px border border-border-pg bg-border-pg sm:grid-cols-3">
          {/* The hero already shows the equity, so these three carry the
              remaining facts: the coin actually held, the official margin
              basis, and the liability that makes equity smaller than it. */}
          <BtcCell
            accent
            title={zh ? "钱包与抵押资产" : "Wallet / collateral"}
            value={fmtBtc(walletBtc, locale, 8)}
            source={zh ? `官方 totalWalletBalance · 按 ${fmtUsd(btcPrice, locale)} 折算 ${fmtUsd(btc.collateral_value_usd, locale)}` : `official totalWalletBalance · ${fmtUsd(btc.collateral_value_usd, locale)} at ${fmtUsd(btcPrice, locale)}`}
          />
          <BtcCell
            title={zh ? "购买力基准（保证金/杠杆）" : "Buying-power basis (margin/leverage)"}
            value={fmtBtc(equityBtc, locale, 8)}
            source={zh ? "官方 accountEquity ÷ BTCUSDT" : "official accountEquity ÷ BTCUSDT"}
          />
          <BtcCell
            title={zh ? "负债（使其低于持币）" : "Liabilities"}
            value={fmtUsd(liabilityUsd, locale)}
            source={zh ? "逐币种净余额为负者之和" : "sum of negative net balances"}
          />
        </div>

        {/* ------------------------------------------------ chart */}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border-pg pt-4">
          <h3 className="text-sm font-semibold">{zh ? "净值表现" : "NAV performance"}</h3>
          <div className="flex items-center gap-0.5 border border-border-pg p-0.5 rounded-lg">
            {(["USD", "BTC"] as const).map((item) => (
              <button key={item} type="button" onClick={() => setCurrency(item)} className={`h-6 px-2.5 text-[10px] font-medium ${currency === item ? "bg-text-pg text-bg-app" : "text-text-pg-dim hover:text-text-pg"}`}>{item}</button>
            ))}
          </div>
        </div>
      </div>

      {usable.length > 1 ? (
        <>
          <div className="h-56 select-none touch-pan-y px-1">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={accent} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={accent} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={(value: number) => new Date(value * 1000).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}
                  tick={{ fill: "var(--muted-2)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={48}
                />
                <YAxis
                  domain={yDomain}
                  tickFormatter={(value: number) => (currency === "USD" ? compactUsd(value) : compactBtc(value))}
                  tick={{ fill: "var(--muted-2)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={52}
                  orientation="right"
                />
                <Tooltip
                  cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
                  content={<NavTooltip locale={locale} currency={currency} />}
                />
                <Area
                  type="linear"
                  dataKey={currency === "USD" ? "netUsd" : "netBtc"}
                  stroke={accent}
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  dot={false}
                  activeDot={{ r: 3.5, fill: accent, stroke: "var(--background)", strokeWidth: 2 }}
                  animationDuration={400}
                  connectNulls={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 pb-4">
            <div className="text-xs">
              {delta !== null ? (
                <span className={`font-medium tabular-nums ${delta >= 0 ? "text-status-positive" : "text-status-negative"}`}>
                  {zh ? "区间净值变化" : "Change over range"}: {signed(delta, (value) => (currency === "USD" ? fmtUsd(value, locale) : fmtBtc(value, locale, 8)))} ({deltaPct === null ? "--" : `${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(2)}%`})
                </span>
              ) : <span className="text-text-pg-muted">{zh ? "区间净值变化: --" : "Change over range: --"}</span>}
            </div>
            <span className="text-[10px] text-text-pg-dim tabular-nums">
              {zh ? `真实快照 ${history?.point_count ?? 0} 点` : `${history?.point_count ?? 0} real snapshots`}
            </span>
          </div>
          <p className="px-5 pb-4 text-[10px] leading-4 text-text-pg-dim">
            {zh
              ? "曲线与上方主数字读同一个字段：官方 actualEquity（市值 − 负债）。主数字下方标注的「市值 − 负债 实测」与「accountEquity」是另外两个口径。"
              : "The curve and the hero above are the same field: official actualEquity (market value − liabilities). The derived figure and accountEquity shown under it are different measures."}
          </p>
        </>
      ) : (
        <div className="mx-5 mb-4 grid h-32 place-items-center border border-border-pg text-sm text-text-pg-muted">
          {history && !history.available
            ? (zh ? "历史数据暂不可用，未绘制曲线。" : "History is unavailable, so no curve is drawn.")
            : (zh ? "数据不足：该区间至少需要 2 个真实快照（不插值、不伪造）。" : "Not enough data in this range: at least two real snapshots are required (no interpolation).")}
        </div>
      )}

      <div className="flex flex-wrap gap-1 px-5 pb-5">
        {RANGES.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setRange(item.key)}
            className={`h-7 min-w-11 px-2 font-mono text-[10px] rounded-lg ${range === item.key ? "border border-status-positive text-status-positive" : "border border-transparent text-text-pg-dim hover:bg-bg-panel-muted"}`}
          >{item.key}</button>
        ))}
      </div>

      {/* ------------------------------------------------ key figures */}
      <div className="grid gap-px border-t border-border-pg bg-border-pg px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label={zh ? "可用资金" : "Available"} value={fmtUsd(availableUsd, locale, 0)} hint={`≈ ${fmtBtc(availableBtc, locale)}`} />
        <Metric label={zh ? "调整后权益" : "Adjusted equity"} value={fmtUsd(adjustedUsd, locale, 0)} hint="actualEquity" />
        <Metric label={zh ? "总敞口（gross）" : "Gross exposure"} value={fmtUsd(exposure.gross_notional_usd, locale, 0)} hint={`≈ ${fmtBtc(exposure.gross_notional_btc_equivalent, locale)}`} />
        <Metric
          label={zh ? "未实现盈亏" : "Unrealized PnL"}
          value={fmtUsd(upnlValue, locale)}
          tone={upnlValue >= 0 ? "positive" : "negative"}
          hint={account.total_unrealized_pnl_usd ? undefined : (zh ? "逐币种汇总" : "summed per asset")}
        />
      </div>

      {/* ------------------------------------------------ secondary metrics */}
      <div className="grid gap-px border-t border-border-pg bg-border-pg sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={zh ? "官方 uniMMR" : "Official uniMMR"} value={num(account.uni_mmr) === null ? "--" : `${fmtBare(num(account.uni_mmr)! * 100, locale)}%`} hint={zh ? "交易所字段，越小越接近风险区" : "exchange field; lower is riskier"} />
        <Stat label={zh ? "维护保证金" : "Maintenance margin"} value={fmtUsd(account.account_maint_margin_usd, locale)} hint={`${zh ? "占权益" : "of equity"} ${fmtBare(num(account.maint_margin_usage_derived) === null ? null : num(account.maint_margin_usage_derived)! * 100, locale)}%`} />
        <Stat label={zh ? "初始保证金" : "Initial margin"} value={fmtUsd(account.account_initial_margin_usd, locale)} hint={`${zh ? "权益缓冲" : "Equity buffer"} ${fmtBare(num(account.equity_buffer_derived) === null ? null : num(account.equity_buffer_derived)! * 100, locale)}%`} />
        <Stat label={zh ? "数据时间" : "As of"} value={view.data_as_of ? new Date(view.data_as_of).toLocaleString(locale) : "--"} hint={zh ? `延迟 ${ageSeconds === null ? "--" : `${Math.round(ageSeconds)}s`}` : `age ${ageSeconds === null ? "--" : `${Math.round(ageSeconds)}s`}`} />
      </div>
    </ResearchCard>

    <ResearchCard className="overflow-hidden p-0">
      <div className="border-b border-border-pg p-5">
        <div className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "币种余额" : "Coin balances"}</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-xs">
          <thead><tr className="border-b border-border-pg text-left text-[10px] uppercase text-text-pg-dim">
            <th className="px-4 py-3 font-medium">{zh ? "币种" : "Asset"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "净余额" : "Net"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "钱包" : "Wallet"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "借入" : "Borrowed"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "利息" : "Interest"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "未实现盈亏" : "Unrealized"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "价值 (USD)" : "Value (USD)"}</th>
            <th className="px-3 py-3 text-right font-medium">≈BTC</th>
            <th className="px-4 py-3 text-right font-medium">{zh ? "价格来源" : "Price source"}</th>
          </tr></thead>
          <tbody className="divide-y divide-border-pg">{balances.map((row) => <tr key={row.asset}>
            <td className="px-4 py-3 font-medium">{row.asset}{row.is_liability ? <span className="ml-2 border border-status-negative px-1.5 py-0.5 text-[10px] text-status-negative rounded-lg">{zh ? "负债" : "LIABILITY"}</span> : null}</td>
            <td className={`px-3 py-3 text-right tabular-nums ${row.is_liability ? "text-status-negative" : ""}`}>{fmtBare(row.net_quantity, locale, 8)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.wallet_balance, locale, 8)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.borrowed, locale, 6)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.interest, locale, 6)}</td>
            <td className={`px-3 py-3 text-right tabular-nums ${(num(row.unrealized_pnl) ?? 0) < 0 ? "text-status-negative" : ""}`}>{fmtBare(row.unrealized_pnl, locale, 4)}</td>
            <td className={`px-3 py-3 text-right tabular-nums ${(num(row.value_usd) ?? 0) < 0 ? "text-status-negative" : ""}`}>{fmtUsd(row.value_usd, locale)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.value_btc_equivalent, locale, 6)}</td>
            <td className="px-4 py-3 text-right text-text-pg-dim">{row.price_source}{row.price_is_approximation ? (zh ? "（近似）" : " (approx)") : ""}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </ResearchCard>

    <ResearchCard className="overflow-hidden p-0">
      <div className="border-b border-border-pg p-5">
        <div className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "实时仓位" : "Live positions"}</div>
        <p className="mt-2 text-xs leading-5 text-text-pg-muted">{zh ? `共 ${positions.length} 笔。notional 取自交易所字段；清算距离按标记价计算。` : `${positions.length} position(s). Notional comes from the exchange; liquidation distance is measured from the mark price.`}</p>
      </div>
      {positions.length ? <div className="overflow-x-auto">
        <table className="w-full min-w-[940px] text-xs">
          <thead><tr className="border-b border-border-pg text-left text-[10px] uppercase text-text-pg-dim">
            <th className="px-4 py-3 font-medium">{zh ? "合约" : "Symbol"}</th>
            <th className="px-3 py-3 font-medium">{zh ? "方向" : "Side"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "数量" : "Qty"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "开仓价" : "Entry"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "标记价" : "Mark"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "清算价" : "Liq."}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "名义价值" : "Notional"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "未实现盈亏" : "Unrealized"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "初始保证金" : "Initial margin"}</th>
            <th className="px-4 py-3 text-right font-medium">{zh ? "杠杆" : "Leverage"}</th>
          </tr></thead>
          <tbody className="divide-y divide-border-pg">{positions.map((row) => <tr key={`${row.product}-${row.symbol}-${row.side}`}>
            <td className="px-4 py-3 font-medium">{row.symbol}<span className="ml-2 text-[10px] uppercase text-text-pg-dim">{row.product}</span></td>
            <td className={`px-3 py-3 ${row.side === "LONG" ? "text-status-positive" : "text-status-negative"}`}>{row.side}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.base_quantity ?? row.quantity, locale, 6)} {row.base_asset ?? ""}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.entry_price, locale, 2)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.mark_price, locale, 2)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{row.has_liquidation_price ? fmtBare(row.liquidation_price, locale, 2) : (zh ? "交易所未提供" : "not provided")}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtUsd(row.notional_usd, locale)}<div className="text-[10px] text-text-pg-dim">≈ {fmtBtc(row.notional_btc_equivalent, locale)}</div></td>
            <td className={`px-3 py-3 text-right tabular-nums ${(num(row.unrealized_pnl) ?? 0) < 0 ? "text-status-negative" : "text-status-positive"}`}>{fmtUsd(row.unrealized_pnl, locale)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{fmtUsd(row.initial_margin_usd, locale)}</td>
            <td className="px-4 py-3 text-right tabular-nums">{row.leverage ?? "--"}x</td>
          </tr>)}</tbody>
        </table>
      </div> : <div className="p-5 text-sm text-text-pg-muted">{zh ? "当前无持仓。" : "No open positions."}</div>}
    </ResearchCard>

    <ResearchCard className="overflow-hidden p-0">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border-pg p-5">
        <div>
          <div className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "历史仓位" : "Position history"}</div>
          <p className="mt-2 text-xs leading-5 text-text-pg-muted">
            {zh
              ? `共 ${historyMeta.count ?? positionHistory.length} 条仓位变更${historyMeta.first_event_at ? `，自 ${new Date(historyMeta.first_event_at).toLocaleString(locale)} 起记录` : ""}。由相邻快照差分得到，不是成交明细。`
              : `${historyMeta.count ?? positionHistory.length} position changes${historyMeta.first_event_at ? ` since ${new Date(historyMeta.first_event_at).toLocaleString(locale)}` : ""}. Derived from snapshot diffs, not fills.`}
          </p>
        </div>
      </div>
      {positionHistory.length ? <div className="max-h-96 overflow-auto">
        <table className="w-full min-w-[820px] text-xs">
          <thead><tr className="border-b border-border-pg text-left text-[10px] uppercase text-text-pg-dim">
            <th className="px-4 py-3 font-medium">{zh ? "时间" : "Time"}</th>
            <th className="px-3 py-3 font-medium">{zh ? "合约" : "Symbol"}</th>
            <th className="px-3 py-3 font-medium">{zh ? "方向" : "Side"}</th>
            <th className="px-3 py-3 font-medium">{zh ? "事件" : "Event"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "数量变化" : "Size"}</th>
            <th className="px-3 py-3 text-right font-medium">{zh ? "名义价值" : "Notional"}</th>
            <th className="px-4 py-3 text-right font-medium">{zh ? "标记价" : "Mark"}</th>
          </tr></thead>
          <tbody className="divide-y divide-border-pg">{positionHistory.map((row, index) => {
            const label = CHANGE_LABEL[row.kind] ?? { zh: row.kind, en: row.kind, tone: "text-text-pg" };
            return <tr key={`${row.captured_at_ms ?? index}-${row.product}-${row.symbol}-${row.kind}`}>
              <td className="px-4 py-3 text-text-pg-muted tabular-nums">{row.captured_at ? new Date(row.captured_at).toLocaleString(locale) : "--"}</td>
              <td className="px-3 py-3 font-medium">{row.symbol}<span className="ml-2 text-[10px] uppercase text-text-pg-dim">{row.product}</span></td>
              <td className={`px-3 py-3 ${row.side === "LONG" ? "text-status-positive" : "text-status-negative"}`}>{row.side}</td>
              <td className={`px-3 py-3 font-medium ${label.tone}`}>{zh ? label.zh : label.en}</td>
              <td className="px-3 py-3 text-right tabular-nums">{fmtBare(row.qty_before, locale, 6)} → {fmtBare(row.qty_after, locale, 6)}</td>
              <td className="px-3 py-3 text-right tabular-nums">{row.notional_usd ? fmtUsd(row.notional_usd, locale) : "--"}</td>
              <td className="px-4 py-3 text-right tabular-nums">{fmtBare(row.mark_price, locale, 2)}</td>
            </tr>;
          })}</tbody>
        </table>
      </div> : <div className="p-5 text-sm text-text-pg-muted">
        {zh ? "尚无仓位变更记录；下一次开仓/加减仓/平仓后开始记录。" : "No position changes recorded yet; recording starts with the next open, resize or close."}
      </div>}
    </ResearchCard>
  </>;
}
