"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CircleAlert,
  CircleCheck,
  CirclePause,
  CircleX,
  KeyRound,
  Landmark,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Badge, DataSourceStatusBadge, StatusDot } from "@/components/puregamma";
import { StatusBadge } from "@/components/ocean/status-badge";
import type { Locale } from "@/i18n/routing";
import { withLocale } from "@/i18n/routing";
import { t, type TranslationKey } from "@/lib/translations";
import {
  cancelLiveOrder,
  confirmLiveOrder,
  createLiveConnection,
  getLiveConnections,
  getLiveOrders,
  getLivePortfolioPositions,
  getTradingMandates,
  getTradingNav,
  getTradingSafetyStatus,
  LiveOrderRejectedError,
  pauseTradingMandate,
  previewLiveOrder,
  testLiveConnection,
  type LiveBrokerConnection,
  type LiveOrderPreviewResult,
  type LiveOrderRow,
  type NavSnapshot,
  type TradingMandate,
  type TradingSafetyStatus,
} from "@/lib/api";
import {
  deriveLiveUiState,
  formatDecimalString,
  isOpenLiveOrderStatus,
  resolveNav,
  type LiveUiState,
} from "@/plugins/builtin/live-trading/state";

export type LiveConsoleView = "overview" | "connect" | "orders" | "account";

const VIEWS: LiveConsoleView[] = ["overview", "connect", "orders", "account"];
const VIEW_ROUTES: Record<LiveConsoleView, string> = {
  overview: "/trading/live",
  connect: "/trading/live/connect",
  orders: "/trading/live/orders",
  account: "/trading/live/account",
};
const VIEW_LABEL_KEYS: Record<LiveConsoleView, TranslationKey> = {
  overview: "live-trading.nav.overview",
  connect: "live-trading.nav.connect",
  orders: "live-trading.nav.orders",
  account: "live-trading.nav.account",
};

type StateNameKey = "pendingApproval" | "killed" | "paused" | "ready" | "liveDisabled" | "unavailable";

const STATE_NAME_KEYS: Record<LiveUiState, StateNameKey> = {
  UNAVAILABLE: "unavailable",
  LIVE_DISABLED: "liveDisabled",
  PENDING_APPROVAL: "pendingApproval",
  KILLED: "killed",
  PAUSED: "paused",
  READY: "ready",
};

function stateTitle(locale: Locale, state: LiveUiState): string {
  const key = STATE_NAME_KEYS[state];
  switch (key) {
    case "unavailable": return t(locale, "live-trading.states.unavailable.title");
    case "liveDisabled": return t(locale, "live-trading.states.liveDisabled.title");
    case "pendingApproval": return t(locale, "live-trading.states.pendingApproval.title");
    case "killed": return t(locale, "live-trading.states.killed.title");
    case "paused": return t(locale, "live-trading.states.paused.title");
    default: return t(locale, "live-trading.states.ready.title");
  }
}

function stateDescription(locale: Locale, state: LiveUiState): string {
  const key = STATE_NAME_KEYS[state];
  switch (key) {
    case "unavailable": return t(locale, "live-trading.states.unavailable.description");
    case "liveDisabled": return t(locale, "live-trading.states.liveDisabled.description");
    case "pendingApproval": return t(locale, "live-trading.states.pendingApproval.description");
    case "killed": return t(locale, "live-trading.states.killed.description");
    case "paused": return t(locale, "live-trading.states.paused.description");
    default: return t(locale, "live-trading.states.ready.description");
  }
}

/**
 * LIVE trading console. One derived state drives every view; the page only
 * displays server state and submits intent — risk math stays server-side.
 */
export function LiveTradingConsole({ locale, view }: { locale: Locale; view: LiveConsoleView }) {
  const [safety, setSafety] = useState<TradingSafetyStatus | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    setUnavailable(false);
    try {
      const result = await getTradingSafetyStatus();
      setSafety(result.safety);
    } catch (error) {
      const status = (error as { status?: number } | null)?.status;
      setSafety(null);
      setUnavailable(status === 404 || status === 501 || !status);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const state = deriveLiveUiState(safety, unavailable);

  if (loading) {
    return (
      <div className="space-y-4">
        <ConsoleTitle locale={locale} />
        <div className="flex items-center gap-2 border border-border-pg bg-bg-panel p-4 text-sm text-text-pg-muted rounded-xl">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t(locale, "live-trading.common.loading")}
        </div>
      </div>
    );
  }

  if (state === "UNAVAILABLE") {
    return (
      <div className="space-y-4">
        <ConsoleTitle locale={locale} />
        <UnavailablePanel locale={locale} onRetry={() => void reload()} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <ConsoleHeader locale={locale} state={state} view={view} onEmergencyReload={() => void reload()} />
      {state === "LIVE_DISABLED" ? (
        <LiveDisabledPanel locale={locale} safety={safety} onRetry={() => void reload()} />
      ) : (
        <>
          <StateBanner locale={locale} state={state} />
          {view === "overview" ? <OverviewView locale={locale} safety={safety} state={state} onReload={() => void reload()} /> : null}
          {view === "connect" ? <ConnectView locale={locale} /> : null}
          {view === "orders" ? <OrdersView locale={locale} state={state} /> : null}
          {view === "account" ? <AccountView locale={locale} /> : null}
        </>
      )}
    </div>
  );
}

// ── Shell pieces ──────────────────────────────────────────────────────────

function ConsoleTitle({ locale }: { locale: Locale }) {
  return (
    <div className="border-b border-border-pg pb-5">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-pg-muted">PureGamma · Live Trading</p>
      <h1 className="mt-2 text-3xl font-semibold md:text-4xl">{t(locale, "live-trading.title")}</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.subtitle")}</p>
    </div>
  );
}

function ConsoleHeader({ locale, state, view, onEmergencyReload }: {
  locale: Locale;
  state: LiveUiState;
  view: LiveConsoleView;
  onEmergencyReload: () => void;
}) {
  const showTabs = state !== "LIVE_DISABLED";
  return (
    <div className="border-b border-border-pg pb-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-pg-muted">PureGamma · Live Trading</p>
          <h1 className="mt-2 text-3xl font-semibold md:text-4xl">{t(locale, "live-trading.title")}</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {state === "READY" ? <StatusBadge domain="trading" value="LIVE" locale={locale} /> : <Badge tone="neutral"><StatusDot tone={state === "LIVE_DISABLED" ? "amber" : "neutral"} />{stateTitle(locale, state)}</Badge>}
          {state !== "LIVE_DISABLED" ? <EmergencyPauseButton locale={locale} onDone={onEmergencyReload} /> : null}
        </div>
      </div>
      {showTabs ? (
        <div className="mt-5 flex gap-2 overflow-x-auto">
          {VIEWS.map((item) => (
            <Link key={item} href={withLocale(locale, VIEW_ROUTES[item])} aria-current={item === view ? "page" : undefined} className={`whitespace-nowrap border px-3 py-2 text-sm rounded-lg ${item === view ? "border-border-pg-strong bg-bg-panel-muted text-text-pg" : "border-border-pg text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"}`}>
              {t(locale, VIEW_LABEL_KEYS[item])}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StateBanner({ locale, state }: { locale: Locale; state: Exclude<LiveUiState, "UNAVAILABLE" | "LIVE_DISABLED"> }) {
  if (state === "READY") return null;
  const tone = state === "KILLED" ? "text-status-negative" : "text-status-warning";
  const Icon = state === "KILLED" ? ShieldAlert : AlertTriangle;
  return (
    <div role="status" className="flex items-start gap-3 border border-border-pg bg-bg-panel p-4 rounded-xl">
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${tone}`} aria-hidden />
      <div>
        <p className={`font-semibold ${tone}`}>{stateTitle(locale, state)}</p>
        <p className="mt-1 text-sm leading-6 text-text-pg-muted">{stateDescription(locale, state)}</p>
      </div>
    </div>
  );
}

function UnavailablePanel({ locale, onRetry }: { locale: Locale; onRetry: () => void }) {
  return (
    <section data-testid="live-unavailable-panel" className="border border-border-pg bg-bg-panel p-6 rounded-xl" role="status">
      <div className="flex items-start gap-3">
        <CircleX className="mt-0.5 h-5 w-5 shrink-0 text-text-pg-muted" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{t(locale, "live-trading.states.unavailable.title")}</h2>
          <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.states.unavailable.description")}</p>
          <p className="mt-2 text-xs leading-5 text-text-pg-dim">{t(locale, "live-trading.states.unavailable.hint")}</p>
          <button type="button" onClick={onRetry} className="mt-4 inline-flex items-center gap-1.5 border border-border-pg px-3 py-2 text-sm hover:border-border-pg-strong rounded-lg">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            {t(locale, "live-trading.common.retry")}
          </button>
        </div>
      </div>
    </section>
  );
}

function LiveDisabledPanel({ locale, safety, onRetry }: { locale: Locale; safety: TradingSafetyStatus | null; onRetry: () => void }) {
  const zh = locale === "zh";
  const checks = safety?.static_gate?.checks || {};
  const approval = safety?.user_live_approval;
  const killSwitches = safety?.kill_switches || [];
  return (
    <div data-testid="live-disabled-panel" className="space-y-4">
      <section className="flex items-start gap-3 border border-status-warning bg-bg-panel-muted p-4 rounded-xl" role="status">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-status-warning">{t(locale, "live-trading.states.liveDisabled.title")}</h2>
          <p className="mt-1 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.description")}</p>
        </div>
        <button type="button" onClick={onRetry} aria-label={t(locale, "live-trading.common.retry")} className="shrink-0 border border-border-pg bg-bg-panel px-2.5 py-1.5 text-xs text-text-pg hover:border-border-pg-strong rounded-lg">
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
        </button>
      </section>

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4">
          <h3 className="font-semibold">{t(locale, "live-trading.states.liveDisabled.staticGate")}</h3>
        </div>
        <div className="divide-y divide-border-pg">
          {Object.keys(checks).length === 0 ? (
            <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p>
          ) : null}
          {Object.entries(checks).map(([name, check]) => (
            <div key={name} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
              <span className="min-w-0 truncate font-mono text-xs text-text-pg-muted">{name}</span>
              <span className={`flex shrink-0 items-center gap-1.5 ${check.ok ? "text-status-positive" : "text-status-warning"}`}>
                {check.ok ? <CircleCheck className="h-3.5 w-3.5" aria-hidden /> : <CircleX className="h-3.5 w-3.5" aria-hidden />}
                {check.ok ? (zh ? "通过" : "ok") : (zh ? "未通过" : "blocked")}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="border border-border-pg bg-bg-panel p-4 rounded-xl">
          <h3 className="font-semibold">{t(locale, "live-trading.states.liveDisabled.approval")}</h3>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-3"><span className="text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.approvalStatus")}</span><span className="font-mono">{approval ? approval.status : zh ? "无记录" : "none"}</span></div>
            <div className="flex justify-between gap-3"><span className="text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.maxNotional")}</span><span className="tabular-nums">{approval && approval.max_total_notional !== "0" ? `$${formatDecimalString(approval.max_total_notional, 2)}` : t(locale, "live-trading.common.noValue")}</span></div>
            <div className="flex justify-between gap-3"><span className="text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.reviewedAt")}</span><span>{approval?.reviewed_at ? new Date(approval.reviewed_at).toLocaleString(locale) : t(locale, "live-trading.states.liveDisabled.neverReviewed")}</span></div>
          </div>
        </div>
        <div className="border border-border-pg bg-bg-panel p-4 rounded-xl">
          <h3 className="font-semibold">{t(locale, "live-trading.states.liveDisabled.killSwitches")}</h3>
          {killSwitches.length === 0 ? (
            <p className="mt-3 text-sm text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.none")}</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {killSwitches.map((item) => (
                <li key={String(item.id)} className="flex items-center justify-between gap-3 text-status-negative">
                  <span className="font-mono text-xs">{String(item.scope)}{item.scope_id ? `:${String(item.scope_id).slice(0, 8)}` : ""}</span>
                  <span className="min-w-0 truncate text-text-pg-muted">{String(item.reason || "")}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="border border-border-pg bg-bg-panel p-5 rounded-xl">
        <h3 className="font-semibold">{t(locale, "live-trading.states.liveDisabled.applyTitle")}</h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.applyDescription")}</p>
        <Link href={withLocale(locale, "/account")} className="mt-4 inline-flex items-center gap-2 border border-border-pg-strong px-3 py-2 text-sm font-medium hover:bg-bg-panel-muted rounded-lg">
          {t(locale, "live-trading.states.liveDisabled.applyLink")}
        </Link>
      </section>
    </div>
  );
}

function EmergencyPauseButton({ locale, onDone }: { locale: Locale; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; count: number; failed: boolean } | null>(null);

  const pauseAll = async () => {
    if (!reason.trim()) return;
    setBusy(true);
    setResult(null);
    let paused = 0;
    let failed = false;
    try {
      const { mandates } = await getTradingMandates();
      const targets = (mandates || []).filter((mandate) => mandate.execution_mode === "live" && !mandate.paused);
      for (const mandate of targets) {
        try {
          await pauseTradingMandate(mandate.id, reason.trim());
          paused += 1;
        } catch {
          failed = true;
        }
      }
      setResult({ ok: targets.length === 0 || !failed, count: paused, failed });
      if (paused > 0) onDone();
    } catch {
      setResult({ ok: false, count: 0, failed: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => { setOpen(!open); setReason(""); setResult(null); }}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 border border-status-warning px-3 py-2 text-sm font-medium text-status-warning hover:bg-bg-panel-muted rounded-lg"
      >
        <CirclePause className="h-4 w-4" aria-hidden />
        {t(locale, "live-trading.emergency.button")}
      </button>
      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-80 border border-status-warning bg-bg-panel p-4 shadow-lg rounded-xl" role="dialog" aria-label={t(locale, "live-trading.emergency.title")}>
          <h3 className="font-semibold text-status-warning">{t(locale, "live-trading.emergency.title")}</h3>
          <p className="mt-2 text-xs leading-5 text-text-pg-muted">{t(locale, "live-trading.emergency.description")}</p>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-label={t(locale, "live-trading.emergency.reasonLabel")}
            placeholder={t(locale, "live-trading.emergency.reasonLabel")}
            className="mt-3 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm rounded-lg"
          />
          <div className="mt-3 flex items-center gap-2">
            <button type="button" onClick={() => void pauseAll()} disabled={!reason.trim() || busy} className="flex-1 border border-status-warning px-3 py-2 text-xs font-semibold text-status-warning disabled:opacity-40 rounded-lg">
              {busy ? t(locale, "live-trading.emergency.running") : t(locale, "live-trading.emergency.confirm")}
            </button>
            <button type="button" onClick={() => setOpen(false)} className="border border-border-pg px-3 py-2 text-xs rounded-lg">
              {t(locale, "live-trading.emergency.cancel")}
            </button>
          </div>
          {result ? (
            <p className={`mt-2 text-xs ${result.ok ? "text-status-positive" : "text-status-negative"}`}>
              {result.ok ? t(locale, "live-trading.emergency.success", { count: result.count }) : t(locale, "live-trading.emergency.failed")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// ── Overview view ─────────────────────────────────────────────────────────

function OverviewView({ locale, safety, state, onReload }: { locale: Locale; safety: TradingSafetyStatus | null; state: LiveUiState; onReload: () => void }) {
  const zh = locale === "zh";
  const [nav, setNav] = useState<NavSnapshot | null>(null);
  const [navError, setNavError] = useState(false);
  const [connections, setConnections] = useState<LiveBrokerConnection[] | null>(null);
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const results = await Promise.allSettled([getTradingNav(), getLiveConnections(), getTradingMandates()]);
    if (results[0].status === "fulfilled") { setNav(results[0].value.nav); setNavError(false); } else setNavError(true);
    if (results[1].status === "fulfilled") setConnections(results[1].value.connections || []);
    if (results[2].status === "fulfilled") setMandates((results[2].value.mandates || []).filter((mandate) => mandate.execution_mode === "live"));
    setBusy(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const navResolution = resolveNav(nav);
  const liveMandates = mandates || [];
  const killSwitches = safety?.kill_switches || [];

  return (
    <div className="space-y-5">
      <section className="grid gap-px border border-border-pg bg-border-pg sm:grid-cols-2 xl:grid-cols-4 rounded-xl overflow-hidden">
        <Field label={t(locale, "live-trading.overview.safetyBar")} value={stateTitle(locale, state)} />
        <Field label={t(locale, "live-trading.overview.navCard")} value={navResolution.kind === "value" ? `${formatDecimalString(navResolution.value, 2)} ${nav?.currency || ""}` : t(locale, "live-trading.common.noValue")} />
        <Field label={t(locale, "live-trading.overview.connections")} value={connections === null ? t(locale, "live-trading.common.loading") : String(connections.length)} />
        <Field label={t(locale, "live-trading.overview.killSwitches")} value={String(killSwitches.length)} />
      </section>

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="flex items-center justify-between gap-3 border-b border-border-pg p-4">
          <h2 className="flex items-center gap-2 font-semibold"><Landmark className="h-4 w-4" aria-hidden />{t(locale, "live-trading.overview.navCard")}</h2>
          <button type="button" onClick={() => { void load(); onReload(); }} disabled={busy} aria-label={t(locale, "live-trading.overview.refresh")} className="border border-border-pg px-2.5 py-1.5 text-xs text-text-pg hover:border-border-pg-strong disabled:opacity-40 rounded-lg">
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} aria-hidden />
          </button>
        </div>
        <div className="p-4">
          {navError || !nav ? (
            <p className="text-sm text-text-pg-muted">{t(locale, "live-trading.overview.navUnavailable")}</p>
          ) : (
            <>
              <p data-testid="live-nav-value" className="text-4xl font-semibold tabular-nums">{navResolution.kind === "value" ? `${formatDecimalString(navResolution.value, 2)} ${nav.currency}` : t(locale, "live-trading.common.noValue")}</p>
              {navResolution.kind !== "value" ? (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-status-warning"><CircleAlert className="h-3.5 w-3.5" aria-hidden />{zh ? "价格快照过期或缺失 —— 不把旧数字当现值。" : "Price snapshot is stale or missing — an old number is never shown as current."}</p>
              ) : null}
              <div className="mt-4 grid gap-px border border-border-pg bg-border-pg sm:grid-cols-2 xl:grid-cols-4 rounded-lg overflow-hidden">
                <Field label={t(locale, "live-trading.overview.cash")} value={`${formatDecimalString(nav.cash, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.overview.grossExposure")} value={`${formatDecimalString(nav.gross_exposure, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.overview.netExposure")} value={`${formatDecimalString(nav.net_exposure, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.overview.realizedPnl")} value={`${formatDecimalString(nav.realized_pnl, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.overview.unrealizedPnl")} value={`${formatDecimalString(nav.unrealized_pnl, 2)} ${nav.currency}`} />
              </div>
            </>
          )}
        </div>
      </section>

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="flex items-center gap-2 font-semibold"><KeyRound className="h-4 w-4" aria-hidden />{t(locale, "live-trading.overview.connections")}</h2></div>
        <div className="divide-y divide-border-pg">
          {connections === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
          {connections !== null && connections.length === 0 ? (
            <div className="p-4">
              <p className="text-sm text-text-pg-muted">{t(locale, "live-trading.overview.noConnections")}</p>
              <Link href={withLocale(locale, VIEW_ROUTES.connect)} className="mt-3 inline-block border border-border-pg px-3 py-2 text-sm hover:border-border-pg-strong rounded-lg">{t(locale, "live-trading.overview.connectCta")}</Link>
            </div>
          ) : null}
          {connections !== null ? connections.map((connection) => (
            <div key={connection.id} className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
              <div className="min-w-0">
                <p className="font-medium">{connection.account_label || connection.provider}</p>
                <p className="mt-0.5 font-mono text-xs text-text-pg-dim">{connection.provider} · {connection.environment} · {t(locale, "live-trading.overview.credentials")}: {connection.has_credentials ? t(locale, "live-trading.overview.credentialSet") : t(locale, "live-trading.overview.credentialMissing")}</p>
              </div>
              <DataSourceStatusBadge status={connection.status} locale={locale} />
            </div>
          )) : null}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="border border-border-pg bg-bg-panel rounded-xl">
          <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.overview.mandates")}</h2></div>
          <div className="divide-y divide-border-pg">
            {mandates === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
            {liveMandates.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.overview.noMandates")}</p> : null}
            {liveMandates.map((mandate) => (
              <div key={mandate.id} className="p-4 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-mono text-xs text-text-pg-muted">Mandate {mandate.id.slice(0, 8)}</p>
                  <div className="flex items-center gap-2 text-xs">
                    <span className={mandate.paused ? "text-status-warning" : "text-status-positive"}>{mandate.paused ? t(locale, "live-trading.overview.mandatePaused") : mandate.status}</span>
                    <span className="text-text-pg-dim">· {t(locale, "live-trading.overview.mandateApproval")}: {mandate.approval_status}</span>
                  </div>
                </div>
                <dl className="mt-3 grid gap-2 text-xs text-text-pg-muted sm:grid-cols-2">
                  <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.overview.mandateMaxTotal")}</dt><dd className="tabular-nums text-text-pg">${formatDecimalString(mandate.max_total_notional, 2)}</dd></div>
                  <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.overview.mandatePerOrder")}</dt><dd className="tabular-nums text-text-pg">${formatDecimalString(mandate.max_per_order_notional, 2)}</dd></div>
                  <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.overview.mandateDailyLoss")}</dt><dd className="tabular-nums text-text-pg">${formatDecimalString(mandate.max_daily_loss, 2)}</dd></div>
                  <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.overview.mandateExpiry")}</dt><dd className="text-text-pg">{mandate.expires_at ? new Date(mandate.expires_at).toLocaleString(locale) : t(locale, "live-trading.account.neverExpires")}</dd></div>
                </dl>
                <p className="mt-2 truncate text-xs text-text-pg-dim">{t(locale, "live-trading.overview.mandateSymbols")}: {(mandate.allowed_symbols || []).join(", ") || t(locale, "live-trading.common.noValue")}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border border-border-pg bg-bg-panel rounded-xl">
          <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.overview.killSwitches")}</h2></div>
          {killSwitches.length === 0 ? (
            <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.states.liveDisabled.none")}</p>
          ) : (
            <ul className="divide-y divide-border-pg">
              {killSwitches.map((item) => (
                <li key={String(item.id)} className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
                  <span className="font-mono text-xs text-status-negative">{String(item.scope)}{item.scope_id ? `:${String(item.scope_id).slice(0, 8)}` : ""}</span>
                  <span className="min-w-0 flex-1 truncate text-right text-xs text-text-pg-muted">{String(item.reason || "")}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

// ── Connect view ──────────────────────────────────────────────────────────

function ConnectView({ locale }: { locale: Locale }) {
  // The only provider this deployment provisions (must equal the server's
  // LIVE_TRADING_PROVIDER); anything else is rejected by the control plane.
  const [provider, setProvider] = useState("binance_spot");
  const [accountLabel, setAccountLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connections, setConnections] = useState<LiveBrokerConnection[] | null>(null);
  const [health, setHealth] = useState<{ connectionId: string; result: { status: string; health: Record<string, unknown> } } | null>(null);
  const [healthError, setHealthError] = useState("");

  const loadConnections = useCallback(async () => {
    try {
      const result = await getLiveConnections();
      setConnections(result.connections || []);
    } catch {
      setConnections([]);
    }
  }, []);

  useEffect(() => { void loadConnections(); }, [loadConnections]);

  const submit = async () => {
    setError("");
    setNotice("");
    if (!provider.trim() || !apiKey.trim() || !apiSecret.trim()) {
      setError(t(locale, "live-trading.connect.requiredFields"));
      return;
    }
    setBusy("bind");
    try {
      // Plaintext lives only in React state for this one submission; it is
      // never written to localStorage/cookies/logs and never leaves this
      // call besides the HTTPS body.
      await createLiveConnection({
        provider: provider.trim(),
        account_label: accountLabel.trim() || provider.trim(),
        api_key: apiKey,
        api_secret: apiSecret,
        passphrase: passphrase.trim() ? passphrase : null,
      });
      setApiKey("");
      setApiSecret("");
      setPassphrase("");
      setNotice(t(locale, "live-trading.connect.success"));
      await loadConnections();
    } catch (cause) {
      const status = (cause as { status?: number } | null)?.status;
      setError(status === 404 || status === 501 ? t(locale, "live-trading.connect.unavailableError") : String((cause as Error)?.message || cause));
    } finally {
      setBusy("");
    }
  };

  const test = async (connection: LiveBrokerConnection) => {
    setBusy(`test:${connection.id}`);
    setHealth(null);
    setHealthError("");
    try {
      const result = await testLiveConnection(connection.id);
      setHealth({ connectionId: connection.id, result: result.health });
    } catch (cause) {
      setHealthError(String((cause as Error)?.message || cause));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-5">
      <section className="flex items-start gap-3 border border-border-pg bg-bg-panel p-4 rounded-xl" role="note">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden />
        <div>
          <p className="text-sm font-semibold">{t(locale, "live-trading.connect.title")}</p>
          <p className="mt-1 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.connect.description")}</p>
          <p className="mt-2 text-xs leading-5 text-status-warning">{t(locale, "live-trading.connect.securityNotice")}</p>
        </div>
      </section>

      <section className="border border-border-pg bg-bg-panel p-5 rounded-xl">
        <h2 className="font-semibold">{t(locale, "live-trading.connect.title")}</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-text-pg-muted">
            {t(locale, "live-trading.connect.provider")}
            <select value={provider} onChange={(event) => setProvider(event.target.value)} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg rounded-lg">
              {["binance_spot"].map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-text-pg-muted">
            {t(locale, "live-trading.connect.accountLabel")}
            <input value={accountLabel} onChange={(event) => setAccountLabel(event.target.value)} autoComplete="off" className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg rounded-lg" />
          </label>
          <label className="text-xs text-text-pg-muted">
            {t(locale, "live-trading.connect.apiKey")}
            <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="off" spellCheck={false} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg rounded-lg" />
          </label>
          <label className="text-xs text-text-pg-muted">
            {t(locale, "live-trading.connect.apiSecret")}
            <input type="password" value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} autoComplete="off" spellCheck={false} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg rounded-lg" />
          </label>
          <label className="text-xs text-text-pg-muted sm:col-span-2">
            {t(locale, "live-trading.connect.passphraseOptional")}
            <input type="password" value={passphrase} onChange={(event) => setPassphrase(event.target.value)} autoComplete="off" spellCheck={false} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg rounded-lg" />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => void submit()} disabled={busy === "bind"} className="inline-flex items-center gap-1.5 border border-border-pg-strong bg-pg-white px-4 py-2 text-sm font-semibold text-pg-black disabled:opacity-40 rounded-lg">
            {busy === "bind" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
            {busy === "bind" ? t(locale, "live-trading.connect.submitting") : t(locale, "live-trading.connect.submit")}
          </button>
        </div>
        {error ? <p className="mt-3 text-sm text-status-negative" role="alert">{error}</p> : null}
        {notice ? <p className="mt-3 text-sm text-status-positive" role="status">{notice}</p> : null}
      </section>

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.connect.connections")}</h2></div>
        <div className="divide-y divide-border-pg">
          {connections === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
          {connections !== null && connections.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.connect.noConnections")}</p> : null}
          {connections !== null ? connections.map((connection) => (
            <div key={connection.id} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">{connection.account_label || connection.provider}</p>
                  <p className="mt-0.5 font-mono text-xs text-text-pg-dim">{connection.provider} · {connection.environment}</p>
                </div>
                <div className="flex items-center gap-2">
                  <DataSourceStatusBadge status={connection.status} locale={locale} />
                  <button type="button" onClick={() => void test(connection)} disabled={busy === `test:${connection.id}`} className="border border-border-pg px-2.5 py-1.5 text-xs hover:border-border-pg-strong disabled:opacity-40 rounded-lg">
                    {busy === `test:${connection.id}` ? t(locale, "live-trading.connect.testing") : t(locale, "live-trading.connect.test")}
                  </button>
                </div>
              </div>
              {health?.connectionId === connection.id ? (
                <div className="mt-3 border border-border-pg bg-bg-panel-muted p-3 rounded-lg">
                  <p className="text-xs font-semibold">{t(locale, "live-trading.connect.healthResult")}: <span className="font-mono">{String(health.result.status)}</span></p>
                  <p className="mt-1 text-xs text-text-pg-muted">{JSON.stringify(health.result.health)}</p>
                  {String(health.result.health.status || "").toUpperCase() === "DISABLED" ? <p className="mt-2 text-xs text-status-warning">{t(locale, "live-trading.connect.healthDisabledNote")}</p> : null}
                </div>
              ) : null}
              {healthError && health?.connectionId === connection.id ? <p className="mt-2 text-xs text-status-negative" role="alert">{healthError}</p> : null}
            </div>
          )) : null}
        </div>
      </section>
    </div>
  );
}

// ── Orders view ───────────────────────────────────────────────────────────

type PreviewRejection = { message: string; status: number; checks: Array<{ check: string; ok: boolean; detail: string }> };

function OrdersView({ locale, state }: { locale: Locale; state: LiveUiState }) {
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);
  const [orders, setOrders] = useState<LiveOrderRow[] | null>(null);
  const [mandateId, setMandateId] = useState("");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [quantity, setQuantity] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState<LiveOrderPreviewResult | null>(null);
  const [rejection, setRejection] = useState<PreviewRejection | null>(null);
  const [token, setToken] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [cancelTarget, setCancelTarget] = useState<LiveOrderRow | null>(null);

  const liveMandates = useMemo(() => (mandates || []).filter((mandate) => mandate.execution_mode === "live"), [mandates]);

  const load = useCallback(async () => {
    const results = await Promise.allSettled([getTradingMandates(), getLiveOrders()]);
    if (results[0].status === "fulfilled") {
      const list = (results[0].value.mandates || []).filter((mandate) => mandate.execution_mode === "live");
      setMandates(list);
      setMandateId((current) => current || list[0]?.id || "");
    }
    if (results[1].status === "fulfilled") setOrders(results[1].value.orders || []);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const runPreview = async () => {
    setError("");
    setNotice("");
    setPreview(null);
    setRejection(null);
    setToken("");
    if (!mandateId || !symbol.trim() || !quantity.trim()) return;
    setBusy("preview");
    try {
      const result = await previewLiveOrder({
        mandate_id: mandateId,
        symbol: symbol.trim().toUpperCase(),
        side,
        quantity: quantity.trim(),
        order_type: orderType,
        limit_price: orderType === "limit" && limitPrice.trim() ? limitPrice.trim() : null,
      });
      setPreview(result);
    } catch (cause) {
      if (cause instanceof LiveOrderRejectedError) {
        setRejection({ message: cause.message, status: cause.status, checks: cause.checks });
      } else {
        setError(String((cause as Error)?.message || cause));
      }
    } finally {
      setBusy("");
    }
  };

  const runConfirm = async () => {
    if (!preview || !token.trim()) return;
    setBusy("confirm");
    setError("");
    try {
      await confirmLiveOrder(preview.intent.id, token.trim());
      setPreview(null);
      setToken("");
      setDialogOpen(false);
      setNotice(t(locale, "live-trading.orders.submitted"));
      await load();
    } catch (cause) {
      setError(t(locale, "live-trading.orders.confirmError"));
      void cause;
    } finally {
      setBusy("");
    }
  };

  const runCancel = async (order: LiveOrderRow) => {
    setBusy(`cancel:${order.client_order_id}`);
    setError("");
    try {
      await cancelLiveOrder(order.client_order_id);
      setCancelTarget(null);
      setNotice(t(locale, "live-trading.orders.cancelDone"));
      await load();
    } catch (cause) {
      setError(String((cause as Error)?.message || cause));
    } finally {
      setBusy("");
    }
  };

  const orderFormEnabled = state === "READY" && liveMandates.length > 0;

  return (
    <div className="space-y-5">
      <section data-testid="live-order-form" className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.orders.formTitle")}</h2></div>
        {!orderFormEnabled ? (
          <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.orders.noMandates")}</p>
        ) : (
          <div className="p-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.mandate")}
                <select value={mandateId} onChange={(event) => setMandateId(event.target.value)} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg rounded-lg">
                  {liveMandates.map((mandate) => <option key={mandate.id} value={mandate.id}>{mandate.id.slice(0, 8)} · {mandate.allowed_symbols?.join(",") || "—"}</option>)}
                </select>
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.symbol")}
                <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} spellCheck={false} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg rounded-lg" />
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.side")}
                <select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg rounded-lg">
                  <option value="buy">{t(locale, "live-trading.orders.buy")}</option>
                  <option value="sell">{t(locale, "live-trading.orders.sell")}</option>
                </select>
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.orderType")}
                <select value={orderType} onChange={(event) => setOrderType(event.target.value as "market" | "limit")} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg rounded-lg">
                  <option value="market">{t(locale, "live-trading.orders.market")}</option>
                  <option value="limit">{t(locale, "live-trading.orders.limit")}</option>
                </select>
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.quantity")}
                <input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="0.00000000" spellCheck={false} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg rounded-lg" />
              </label>
              {orderType === "limit" ? (
                <label className="text-xs text-text-pg-muted">
                  {t(locale, "live-trading.orders.limitPrice")}
                  <input inputMode="decimal" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} placeholder="0.00" spellCheck={false} className="mt-1 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg rounded-lg" />
                </label>
              ) : null}
            </div>
            <button type="button" onClick={() => void runPreview()} disabled={busy === "preview"} className="mt-4 inline-flex items-center gap-1.5 border border-border-pg px-4 py-2 text-sm font-medium hover:border-border-pg-strong disabled:opacity-40 rounded-lg">
              {busy === "preview" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
              {busy === "preview" ? t(locale, "live-trading.orders.previewing") : t(locale, "live-trading.orders.preview")}
            </button>
          </div>
        )}
      </section>

      {error ? <p className="text-sm text-status-negative" role="alert">{error}</p> : null}
      {notice ? <p className="text-sm text-status-positive" role="status">{notice}</p> : null}

      {rejection ? (
        <section data-testid="live-preview-rejection" className="border border-status-negative bg-bg-panel p-4 rounded-xl" role="alert">
          <div className="flex items-start gap-3">
            <CircleX className="mt-0.5 h-5 w-5 shrink-0 text-status-negative" aria-hidden />
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold text-status-negative">{t(locale, "live-trading.orders.rejectedTitle")}</h3>
              <p className="mt-1 text-sm text-text-pg-muted">{rejection.message}</p>
              <p className="mt-1 text-xs text-status-warning">{t(locale, "live-trading.orders.rejectedHint")}</p>
            </div>
          </div>
          <div className="mt-4 overflow-x-auto border border-border-pg rounded-lg">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  <th className="p-2.5 font-medium">{t(locale, "live-trading.orders.riskChecks")}</th>
                  <th className="p-2.5 font-medium">{t(locale, "live-trading.states.liveDisabled.approvalStatus")}</th>
                  <th className="p-2.5 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {rejection.checks.map((check) => (
                  <tr key={check.check} className="border-b border-border-pg last:border-0">
                    <td className="p-2.5 font-mono text-xs">{check.check}</td>
                    <td className={`p-2.5 text-xs ${check.ok ? "text-status-positive" : "text-status-negative"}`}>{check.ok ? t(locale, "live-trading.orders.pass") : t(locale, "live-trading.orders.reject")}</td>
                    <td className="p-2.5 text-xs text-text-pg-muted">{check.detail}</td>
                  </tr>
                ))}
                {rejection.checks.length === 0 ? (
                  <tr><td colSpan={3} className="p-3 text-xs text-text-pg-muted">{rejection.message}</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {preview ? (
        <section className="border border-status-warning bg-bg-panel p-4 rounded-xl">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden />
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold">{t(locale, "live-trading.orders.intent")}</h3>
              <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogSymbol")}</dt><dd className="font-mono">{preview.intent.symbol}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogSide")}</dt><dd>{preview.intent.side}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogQuantity")}</dt><dd className="font-mono tabular-nums">{preview.intent.quantity}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogType")}</dt><dd>{preview.intent.order_type}{preview.intent.limit_price ? ` @ ${preview.intent.limit_price}` : ""}</dd></div>
                <div className="flex justify-between gap-3 sm:col-span-2"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.traceId")}</dt><dd className="min-w-0 truncate font-mono text-xs">{preview.trace_id}</dd></div>
              </dl>
              <p className="mt-3 text-xs text-text-pg-muted">{t(locale, "live-trading.orders.confirmationToken")}</p>
              <code className="mt-2 block overflow-x-auto border border-border-pg bg-bg-panel-muted p-3 text-xs rounded-lg">{preview.confirmation}</code>
              <input value={token} onChange={(event) => setToken(event.target.value)} aria-label={t(locale, "live-trading.orders.confirmationInput")} placeholder={t(locale, "live-trading.orders.confirmationInput")} autoComplete="off" spellCheck={false} className="mt-3 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm rounded-lg" />
              <button type="button" onClick={() => setDialogOpen(true)} disabled={!token.trim() || busy === "confirm"} className="mt-3 border border-status-warning px-4 py-2 text-sm font-semibold text-status-warning disabled:opacity-40 rounded-lg">
                {t(locale, "live-trading.orders.confirm")}
              </button>
            </div>
          </div>
        </section>
      ) : null}

      {dialogOpen && preview ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label={t(locale, "live-trading.orders.confirmDialogTitle")}>
          <div className="w-full max-w-md border border-status-warning bg-bg-panel p-5 rounded-xl">
            <h3 className="font-semibold text-status-warning">{t(locale, "live-trading.orders.confirmDialogTitle")}</h3>
            <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.orders.confirmDialogBody")}</p>
            <dl className="mt-4 space-y-2 border border-border-pg bg-bg-panel-muted p-3 text-sm rounded-lg">
              <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogSymbol")}</dt><dd className="font-mono">{preview.intent.symbol}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogSide")}</dt><dd>{preview.intent.side}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogQuantity")}</dt><dd className="font-mono tabular-nums">{preview.intent.quantity}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogType")}</dt><dd>{preview.intent.order_type}</dd></div>
              {preview.intent.limit_price ? <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogLimitPrice")}</dt><dd className="font-mono tabular-nums">{preview.intent.limit_price}</dd></div> : null}
              <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogVenue")}</dt><dd>{t(locale, "live-trading.orders.dialogVenueValue")}</dd></div>
            </dl>
            <div className="mt-4 flex gap-2">
              <button type="button" onClick={() => setDialogOpen(false)} className="flex-1 border border-border-pg px-3 py-2 text-sm rounded-lg">{t(locale, "live-trading.orders.dialogBack")}</button>
              <button type="button" onClick={() => void runConfirm()} disabled={busy === "confirm"} className="flex-1 border border-status-warning px-3 py-2 text-sm font-semibold text-status-warning disabled:opacity-40 rounded-lg">
                {busy === "confirm" ? <Loader2 className="mx-auto h-4 w-4 animate-spin" aria-hidden /> : t(locale, "live-trading.orders.dialogConfirm")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.orders.listTitle")}</h2></div>
        {orders === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
        {orders !== null && orders.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.orders.empty")}</p> : null}
        {orders !== null && orders.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  {[t(locale, "live-trading.orders.colCreated"), t(locale, "live-trading.orders.colSymbol"), t(locale, "live-trading.orders.colSide"), t(locale, "live-trading.orders.colQuantity"), t(locale, "live-trading.orders.colType"), t(locale, "live-trading.orders.colStatus"), t(locale, "live-trading.orders.colFilled"), t(locale, "live-trading.orders.colClientOrderId"), t(locale, "live-trading.orders.colBrokerOrderId"), t(locale, "live-trading.orders.colActions")].map((head) => <th key={head} className="p-2.5 font-medium">{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id} className="border-b border-border-pg align-top last:border-0">
                    <td className="p-2.5 text-xs text-text-pg-muted">{new Date(order.created_at).toLocaleString(locale)}</td>
                    <td className="p-2.5 font-mono text-xs font-semibold">{order.symbol}</td>
                    <td className="p-2.5 text-xs">{order.side}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(order.quantity)}</td>
                    <td className="p-2.5 text-xs">{order.order_type}</td>
                    <td className="p-2.5"><OrderStatusBadge status={order.status} locale={locale} /></td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(order.filled_quantity)}</td>
                    <td className="p-2.5 font-mono text-xs text-text-pg-muted">{order.client_order_id}</td>
                    <td className="p-2.5 font-mono text-xs text-text-pg-muted">{order.broker_order_id || t(locale, "live-trading.common.noValue")}</td>
                    <td className="p-2.5">
                      {isOpenLiveOrderStatus(order.status) ? (
                        <button type="button" onClick={() => setCancelTarget(order)} className="border border-border-pg px-2 py-1 text-xs text-status-warning hover:border-border-pg-strong rounded-lg">{t(locale, "live-trading.orders.cancel")}</button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="border border-border-pg bg-bg-panel p-4 rounded-xl">
        <h3 className="font-semibold">{t(locale, "live-trading.orders.fillsTitle")}</h3>
        <p className="mt-2 text-sm text-text-pg-muted">{t(locale, "live-trading.orders.fillsUnavailable")}</p>
      </section>

      {cancelTarget ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label={t(locale, "live-trading.orders.cancelConfirmTitle")}>
          <div className="w-full max-w-md border border-status-warning bg-bg-panel p-5 rounded-xl">
            <h3 className="font-semibold text-status-warning">{t(locale, "live-trading.orders.cancelConfirmTitle")}</h3>
            <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.orders.cancelConfirmBody")}</p>
            <p className="mt-3 font-mono text-xs text-text-pg-muted">{cancelTarget.symbol} · {cancelTarget.side} · {formatDecimalString(cancelTarget.quantity)} · {cancelTarget.client_order_id}</p>
            <div className="mt-4 flex gap-2">
              <button type="button" onClick={() => setCancelTarget(null)} className="flex-1 border border-border-pg px-3 py-2 text-sm rounded-lg">{t(locale, "live-trading.orders.dialogBack")}</button>
              <button type="button" onClick={() => void runCancel(cancelTarget)} disabled={busy === `cancel:${cancelTarget.client_order_id}`} className="flex-1 border border-status-warning px-3 py-2 text-sm font-semibold text-status-warning disabled:opacity-40 rounded-lg">{t(locale, "live-trading.orders.cancel")}</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function OrderStatusBadge({ status, locale }: { status: string; locale: Locale }) {
  const normalized = (status || "").toLowerCase();
  const tone = normalized === "filled" ? "text-status-positive" : normalized === "partially_filled" || normalized === "pending" || normalized === "accepted" || normalized === "submitted" ? "text-text-pg" : normalized === "unknown" ? "text-status-warning" : "text-text-pg-dim";
  return <span className={`inline-flex items-center gap-1 border border-border-pg bg-bg-panel-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tone}`}>{status}</span>;
}

// ── Account view ──────────────────────────────────────────────────────────

function AccountView({ locale }: { locale: Locale }) {
  const [nav, setNav] = useState<NavSnapshot | null>(null);
  const [positions, setPositions] = useState<Array<{ symbol: string; quantity: string; mark_price: string | null; market_value: string | null; stale: boolean }> | null>(null);
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);

  useEffect(() => {
    void (async () => {
      const results = await Promise.allSettled([getTradingNav(), getLivePortfolioPositions(), getTradingMandates()]);
      if (results[0].status === "fulfilled") setNav(results[0].value.nav);
      if (results[1].status === "fulfilled") setPositions(results[1].value.positions || []);
      if (results[2].status === "fulfilled") setMandates((results[2].value.mandates || []).filter((mandate) => mandate.execution_mode === "live"));
    })();
  }, []);

  const navResolution = resolveNav(nav);
  const liveMandates = mandates || [];

  return (
    <div className="space-y-5">
      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.account.balances")}</h2></div>
        <div className="p-4">
          {!nav ? (
            <p className="text-sm text-text-pg-muted">{t(locale, "live-trading.overview.navUnavailable")}</p>
          ) : (
            <>
              <p className="text-4xl font-semibold tabular-nums">{navResolution.kind === "value" ? `${formatDecimalString(navResolution.value, 2)} ${nav.currency}` : t(locale, "live-trading.common.noValue")}</p>
              {navResolution.kind !== "value" ? <p className="mt-2 text-xs text-status-warning">{t(locale, "live-trading.common.noValue")} — NAV stale / NULL</p> : null}
              <div className="mt-4 grid gap-px border border-border-pg bg-border-pg sm:grid-cols-2 xl:grid-cols-4 rounded-lg overflow-hidden">
                <Field label={t(locale, "live-trading.account.cash")} value={`${formatDecimalString(nav.cash, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.account.realizedPnl")} value={`${formatDecimalString(nav.realized_pnl, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.account.unrealizedPnl")} value={`${formatDecimalString(nav.unrealized_pnl, 2)} ${nav.currency}`} />
                <Field label={t(locale, "live-trading.account.reconciliation")} value={reconciliationLabel(nav.reconciliation_status, locale)} />
              </div>
            </>
          )}
        </div>
      </section>

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.account.positions")}</h2></div>
        {positions === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
        {positions !== null && positions.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.account.positionsEmpty")}</p> : null}
        {positions !== null && positions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  {[t(locale, "live-trading.account.colSymbol"), t(locale, "live-trading.account.colQuantity"), t(locale, "live-trading.account.colMark"), t(locale, "live-trading.account.colValue")].map((head) => <th key={head} className="p-2.5 font-medium">{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.symbol} className="border-b border-border-pg last:border-0">
                    <td className="p-2.5 font-mono text-xs font-semibold">{position.symbol}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(position.quantity)}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{position.mark_price == null ? t(locale, "live-trading.common.noValue") : formatDecimalString(position.mark_price)}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{position.market_value == null ? t(locale, "live-trading.common.noValue") : formatDecimalString(position.market_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="border border-border-pg bg-bg-panel p-4 rounded-xl">
        <h3 className="font-semibold">{t(locale, "live-trading.account.ledger")}</h3>
        <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.account.ledgerUnavailable")}</p>
      </section>

      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.account.mandates")}</h2></div>
        <div className="divide-y divide-border-pg">
          {mandates === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
          {liveMandates.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.account.noMandates")}</p> : null}
          {liveMandates.map((mandate) => (
            <div key={mandate.id} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <p className="font-mono text-text-pg-muted">Mandate {mandate.id.slice(0, 8)}</p>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={mandate.paused ? "text-status-warning" : "text-status-positive"}>{mandate.paused ? t(locale, "live-trading.account.mandatePaused") : mandate.status}</span>
                  <span className="text-text-pg-dim">· {t(locale, "live-trading.account.mandateApproval")}: {mandate.approval_status}</span>
                </div>
              </div>
              {mandate.pause_reason ? <p className="mt-2 text-xs text-status-warning">{t(locale, "live-trading.account.mandatePauseReason")}: {mandate.pause_reason}</p> : null}
              <div className="mt-3 grid gap-px border border-border-pg bg-border-pg sm:grid-cols-2 xl:grid-cols-4 rounded-lg overflow-hidden">
                <Field label={t(locale, "live-trading.account.mandateMaxTotal")} value={`$${formatDecimalString(mandate.max_total_notional, 2)}`} />
                <Field label={t(locale, "live-trading.account.mandatePerOrder")} value={`$${formatDecimalString(mandate.max_per_order_notional, 2)}`} />
                <Field label={t(locale, "live-trading.account.mandatePosition")} value={`$${formatDecimalString(mandate.max_position_notional, 2)}`} />
                <Field label={t(locale, "live-trading.account.mandateDailyLoss")} value={`$${formatDecimalString(mandate.max_daily_loss, 2)}`} />
                <Field label={t(locale, "live-trading.account.mandateLeverage")} value={`${mandate.max_leverage}x`} />
                <Field label={t(locale, "live-trading.account.mandateTradesPerDay")} value={mandate.max_trades_per_day == null ? t(locale, "live-trading.common.noValue") : String(mandate.max_trades_per_day)} />
                <Field label={t(locale, "live-trading.account.mandateFrequency")} value={mandate.max_order_frequency_seconds == null ? t(locale, "live-trading.common.noValue") : t(locale, "live-trading.account.mandateFrequencyValue", { seconds: mandate.max_order_frequency_seconds })} />
                <Field label={t(locale, "live-trading.account.mandateExpiry")} value={mandate.expires_at ? new Date(mandate.expires_at).toLocaleString(locale) : t(locale, "live-trading.account.neverExpires")} />
              </div>
              <p className="mt-2 truncate text-xs text-text-pg-dim">{t(locale, "live-trading.account.mandateWhitelist")}: {(mandate.allowed_symbols || []).join(", ") || t(locale, "live-trading.common.noValue")}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function reconciliationLabel(status: string, locale: Locale): string {
  const zh = locale === "zh";
  if (status === "ok") return zh ? "正常" : "ok";
  if (status === "pending") return zh ? "待处理" : "pending";
  if (status === "mismatch") return zh ? "存在差异（已暂停 Mandate）" : "mismatch (mandate paused)";
  return status || t(locale, "live-trading.common.noValue");
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-panel p-3">
      <p className="text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</p>
      <p className="mt-1 break-words text-sm font-medium tabular-nums text-text-pg">{value}</p>
    </div>
  );
}
