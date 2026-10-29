"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { hasTranslation, t, type TranslationKey } from "@/lib/translations";
import {
  cancelLiveOrder,
  confirmLiveOrder,
  createLiveConnection,
  describeApiError,
  getLiveConnections,
  getLiveFills,
  getLiveLedger,
  getLiveOrders,
  getLiveOrderSyncStatus,
  getLiveReconciliation,
  getLivePortfolioPositions,
  getTradingMandates,
  getTradingNav,
  getTradingSafetyStatus,
  LiveOrderRejectedError,
  pauseTradingMandate,
  previewLiveOrder,
  recheckLiveOrder,
  resumeTradingMandate,
  revokeLiveConnection,
  testLiveConnection,
  type LiveBrokerConnection,
  type LiveFillRow,
  type LiveLedgerEntry,
  type LiveOrderPreviewResult,
  type LiveOrderRow,
  type LiveOrderSyncStatus,
  type LiveReconciliationView,
  type NavSnapshot,
  type TradingMandate,
  type TradingSafetyStatus,
} from "@/lib/api";
import {
  classifySubmitFailure,
  deriveLiveUiState,
  displayHealthRows,
  formatDecimalString,
  isOpenLiveOrderStatus,
  isUnknownLiveOrderStatus,
  multiplyDecimalStrings,
  resolveNav,
  secondsUntil,
  type LiveUiState,
} from "@/plugins/builtin/live-trading/state";
import { useDialogFocus } from "@/lib/use-dialog-focus";

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
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
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
          {view === "orders" ? <OrdersView locale={locale} state={state} safety={safety} /> : null}
          {view === "account" ? <AccountView locale={locale} safety={safety} onReload={() => void reload()} /> : null}
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
  const [results, setResults] = useState<Array<{ id: string; ok: boolean }> | null>(null);
  const [listFailed, setListFailed] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const close = useCallback(() => setOpen(false), []);
  useDialogFocus(open, panelRef, close);

  const pauseAll = async () => {
    if (!reason.trim()) return;
    setBusy(true);
    setResults(null);
    setListFailed(false);
    try {
      const { mandates } = await getTradingMandates();
      const targets = (mandates || []).filter((mandate) => mandate.execution_mode === "live" && !mandate.paused);
      const outcome: Array<{ id: string; ok: boolean }> = [];
      // Sequential on purpose: each pause takes the mandate row lock, and a
      // per-mandate result tells the user exactly which one still trades.
      for (const mandate of targets) {
        try {
          await pauseTradingMandate(mandate.id, reason.trim());
          outcome.push({ id: mandate.id, ok: true });
        } catch {
          outcome.push({ id: mandate.id, ok: false });
        }
      }
      setResults(outcome);
      if (outcome.some((item) => item.ok)) onDone();
    } catch {
      setListFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const failedCount = results?.filter((item) => !item.ok).length ?? 0;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => { setOpen(!open); setReason(""); setResults(null); setListFailed(false); }}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-status-warning px-3 text-sm font-medium text-status-warning hover:bg-bg-panel-muted"
      >
        <CirclePause className="h-4 w-4" aria-hidden />
        {t(locale, "live-trading.emergency.button")}
      </button>
      {open ? (
        <div ref={panelRef} className="absolute right-0 z-30 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-xl border border-status-warning bg-bg-panel p-4 shadow-lg" role="dialog" aria-modal="false" aria-label={t(locale, "live-trading.emergency.title")}>
          <h3 className="font-semibold text-status-warning">{t(locale, "live-trading.emergency.title")}</h3>
          <p className="mt-2 text-xs leading-5 text-text-pg-muted">{t(locale, "live-trading.emergency.description")}</p>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-label={t(locale, "live-trading.emergency.reasonLabel")}
            placeholder={t(locale, "live-trading.emergency.reasonLabel")}
            className="mt-3 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm"
          />
          <div className="mt-3 flex items-center gap-2">
            <button type="button" onClick={() => void pauseAll()} disabled={!reason.trim() || busy} className="min-h-10 flex-1 rounded-lg border border-status-warning px-3 text-xs font-semibold text-status-warning disabled:opacity-40">
              {busy ? t(locale, "live-trading.emergency.running") : t(locale, "live-trading.emergency.confirm")}
            </button>
            <button type="button" onClick={close} className="min-h-10 rounded-lg border border-border-pg px-3 text-xs">
              {t(locale, "live-trading.emergency.cancel")}
            </button>
          </div>
          {listFailed ? <p role="alert" className="mt-2 text-xs text-status-negative">{t(locale, "live-trading.emergency.failed")}</p> : null}
          {results ? (
            <div role="status" className="mt-2 space-y-1 text-xs">
              <p className={failedCount ? "text-status-negative" : "text-status-positive"}>
                {failedCount ? t(locale, "live-trading.emergency.failed") : t(locale, "live-trading.emergency.success", { count: results.length })}
              </p>
              <ul className="space-y-0.5">
                {results.map((item) => (
                  <li key={item.id} className={`font-mono ${item.ok ? "text-text-pg-muted" : "text-status-negative"}`}>
                    {item.ok ? t(locale, "live-trading.workflow.emergencyResult.paused", { id: item.id.slice(0, 8) }) : t(locale, "live-trading.workflow.emergencyResult.failed", { id: item.id.slice(0, 8) })}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// ── NAV ───────────────────────────────────────────────────────────────────

type NavLoad = { kind: "loading" } | { kind: "no-account" } | { kind: "error" } | { kind: "ready"; nav: NavSnapshot };

async function loadNav(): Promise<NavLoad> {
  try {
    const { nav } = await getTradingNav();
    return nav ? { kind: "ready", nav } : { kind: "error" };
  } catch (error) {
    const { status, code } = describeApiError(error);
    return status === 404 && code === "TRADING_ACCOUNT_NOT_FOUND" ? { kind: "no-account" } : { kind: "error" };
  }
}

/**
 * Server NAV with its provenance. A stale or missing NAV renders as "—";
 * components of a stale snapshot stay visible but are labelled with the time
 * they are from, and "no account" is never shown as a zero.
 */
function NavPanel({ locale, load, extra }: { locale: Locale; load: NavLoad; extra?: (nav: NavSnapshot) => Array<{ label: string; value: string }> }) {
  if (load.kind === "loading") return <p className="text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p>;
  if (load.kind === "no-account") return <p data-testid="live-nav-no-account" className="text-sm text-text-pg-muted">{t(locale, "live-trading.workflow.nav.noAccount")}</p>;
  if (load.kind === "error") return <p className="text-sm text-text-pg-muted">{t(locale, "live-trading.overview.navUnavailable")}</p>;
  const nav = load.nav;
  const resolution = resolveNav(nav);
  const money = (value: string | null | undefined) => (value == null ? t(locale, "live-trading.common.noValue") : `${formatDecimalString(value, 2)} ${nav.currency}`);
  const calculated = new Date(nav.calculated_at).toLocaleString(locale);
  const fields = [
    { label: t(locale, "live-trading.overview.cash"), value: money(nav.cash) },
    { label: t(locale, "live-trading.overview.grossExposure"), value: money(nav.gross_exposure) },
    { label: t(locale, "live-trading.overview.netExposure"), value: money(nav.net_exposure) },
    { label: t(locale, "live-trading.overview.realizedPnl"), value: money(nav.realized_pnl) },
    { label: t(locale, "live-trading.overview.unrealizedPnl"), value: money(nav.unrealized_pnl) },
    ...(extra ? extra(nav) : []),
  ];
  return (
    <>
      <p data-testid="live-nav-value" className="text-4xl font-semibold tabular-nums">{resolution.kind === "value" ? money(resolution.value) : t(locale, "live-trading.common.noValue")}</p>
      <p className="mt-2 text-xs text-text-pg-dim" data-testid="live-nav-provenance">{t(locale, "live-trading.workflow.nav.provenance", { currency: nav.currency, version: nav.calculation_version })}</p>
      <p className="mt-0.5 text-xs text-text-pg-dim">{t(locale, "live-trading.workflow.nav.asOf", { calculated, price: nav.price_timestamp ? new Date(nav.price_timestamp).toLocaleString(locale) : t(locale, "live-trading.workflow.nav.noPrice") })}</p>
      {resolution.kind !== "value" ? (
        <p role="status" data-testid="live-nav-stale" className="mt-2 flex items-center gap-1.5 text-xs text-status-warning"><CircleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden />{t(locale, "live-trading.workflow.nav.staleComponents", { calculated })}</p>
      ) : null}
      <div className={`mt-4 grid gap-px overflow-hidden rounded-lg border border-border-pg bg-border-pg sm:grid-cols-2 xl:grid-cols-4 ${resolution.kind !== "value" ? "opacity-80" : ""}`}>
        {fields.map((field) => <Field key={field.label} label={field.label} value={field.value} />)}
      </div>
    </>
  );
}

// ── Overview view ─────────────────────────────────────────────────────────

function OverviewView({ locale, safety, state, onReload }: { locale: Locale; safety: TradingSafetyStatus | null; state: LiveUiState; onReload: () => void }) {
  const zh = locale === "zh";
  const [navLoad, setNavLoad] = useState<NavLoad>({ kind: "loading" });
  const [connections, setConnections] = useState<LiveBrokerConnection[] | null>(null);
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    const [navResult, connectionResult, mandateResult] = await Promise.all([loadNav(), getLiveConnections().catch(() => null), getTradingMandates().catch(() => null)]);
    setNavLoad(navResult);
    if (connectionResult) setConnections(connectionResult.connections || []);
    if (mandateResult) setMandates((mandateResult.mandates || []).filter((mandate) => mandate.execution_mode === "live"));
    setBusy(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const nav = navLoad.kind === "ready" ? navLoad.nav : null;
  const navResolution = resolveNav(nav);
  const liveMandates = mandates || [];
  const killSwitches = safety?.kill_switches || [];

  return (
    <div className="space-y-5">
      {notice ? <p role="status" className="text-sm text-status-positive" data-testid="live-overview-notice">{notice}</p> : null}
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
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin motion-reduce:animate-none" : ""}`} aria-hidden />
          </button>
        </div>
        <div className="p-4">
          <NavPanel locale={locale} load={navLoad} />
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
                <MandateGateList locale={locale} gate={safety?.mandates?.[mandate.id]} />
                {mandate.paused ? <div className="mt-3"><ResumeMandate locale={locale} mandate={mandate} killSwitchEngaged={killSwitches.length > 0} onDone={() => { setNotice(t(locale, "live-trading.workflow.resume.done")); void load(); onReload(); }} /></div> : null}
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
  const [revokeTarget, setRevokeTarget] = useState<LiveBrokerConnection | null>(null);

  const revoke = async (connection: LiveBrokerConnection) => {
    setBusy(`revoke:${connection.id}`);
    setError("");
    setNotice("");
    try {
      await revokeLiveConnection(connection.id);
      setRevokeTarget(null);
      setNotice(t(locale, "live-trading.workflow.revoke.done"));
      await loadConnections();
    } catch (cause) {
      setError(describeApiError(cause).message);
    } finally {
      setBusy("");
    }
  };

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
      setError(status === 404 || status === 501 ? t(locale, "live-trading.connect.unavailableError") : describeApiError(cause).message);
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
      setHealthError(describeApiError(cause).message);
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
          <button type="button" onClick={() => void submit()} disabled={busy === "bind"} className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-[var(--pg-surface-inverse)] px-4 text-sm font-semibold text-[var(--pg-text-inverse)] disabled:opacity-40">
            {busy === "bind" ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : null}
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
                  {connection.revoked_at ? <span className="text-xs text-text-pg-dim">{t(locale, "live-trading.workflow.revoke.revoked")}</span> : (
                    <>
                      <button type="button" onClick={() => void test(connection)} disabled={busy === `test:${connection.id}`} className="min-h-9 rounded-lg border border-border-pg px-2.5 text-xs hover:border-border-pg-strong disabled:opacity-40">
                        {busy === `test:${connection.id}` ? t(locale, "live-trading.connect.testing") : t(locale, "live-trading.connect.test")}
                      </button>
                      <button type="button" onClick={() => setRevokeTarget(connection)} className="min-h-9 rounded-lg border border-border-pg px-2.5 text-xs text-status-negative hover:border-status-negative">
                        {t(locale, "live-trading.workflow.revoke.button")}
                      </button>
                    </>
                  )}
                </div>
              </div>
              {health?.connectionId === connection.id ? (
                <div className="mt-3 border border-border-pg bg-bg-panel-muted p-3 rounded-lg">
                  <p className="text-xs font-semibold">{t(locale, "live-trading.connect.healthResult")}: <span className="font-mono">{String(health.result.status)}</span></p>
                  <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2" data-testid="live-connection-health">
                    {displayHealthRows(health.result.health).map((row) => (
                      <div key={row.key} className="flex min-w-0 justify-between gap-3"><dt className="font-mono text-text-pg-dim">{row.key}</dt><dd className="min-w-0 truncate text-right text-text-pg-muted">{row.value}</dd></div>
                    ))}
                  </dl>
                  {String(health.result.health.status || "").toUpperCase() === "DISABLED" ? <p className="mt-2 text-xs text-status-warning">{t(locale, "live-trading.connect.healthDisabledNote")}</p> : null}
                </div>
              ) : null}
              {healthError && health?.connectionId === connection.id ? <p className="mt-2 text-xs text-status-negative" role="alert">{healthError}</p> : null}
            </div>
          )) : null}
        </div>
      </section>
      {revokeTarget ? <RevokeConnectionDialog locale={locale} connection={revokeTarget} busy={busy === `revoke:${revokeTarget.id}`} onBack={() => setRevokeTarget(null)} onConfirm={() => void revoke(revokeTarget)} /> : null}
    </div>
  );
}

function RevokeConnectionDialog({ locale, connection, busy, onBack, onConfirm }: { locale: Locale; connection: LiveBrokerConnection; busy: boolean; onBack: () => void; onConfirm: () => void }) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backRef = useRef<HTMLButtonElement | null>(null);
  useDialogFocus(true, panelRef, onBack, backRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="live-revoke-title" className="w-full max-w-md rounded-xl border border-status-negative bg-bg-panel p-5">
        <h3 id="live-revoke-title" className="font-semibold text-status-negative">{t(locale, "live-trading.workflow.revoke.title")}</h3>
        <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.workflow.revoke.body")}</p>
        <p className="mt-3 font-mono text-xs text-text-pg-muted">{connection.account_label || connection.provider} · {connection.provider} · {connection.environment}</p>
        <div className="mt-4 flex gap-2">
          <button ref={backRef} type="button" onClick={onBack} className="min-h-10 flex-1 rounded-lg border border-border-pg px-3 text-sm">{t(locale, "live-trading.orders.dialogBack")}</button>
          <button type="button" onClick={onConfirm} disabled={busy} className="min-h-10 flex-1 rounded-lg border border-status-negative px-3 text-sm font-semibold text-status-negative disabled:opacity-40">{t(locale, "live-trading.workflow.revoke.button")}</button>
        </div>
      </div>
    </div>
  );
}

// ── Orders view ───────────────────────────────────────────────────────────

type PreviewRejection = { message: string; status: number; checks: Array<{ check: string; ok: boolean; detail: string }> };

/**
 * Where a confirmed intent stands. "ambiguous" is the important one: the
 * request got no definite answer, so the order may exist at the venue. The
 * console then only reconciles or re-sends the SAME intent (the control plane
 * returns the existing order for an intent it already accepted) and blocks a
 * fresh preview for the same trade until the user resolves it.
 */
type Submission =
  | { state: "submitting"; preview: LiveOrderPreviewResult; token: string }
  | { state: "ambiguous"; preview: LiveOrderPreviewResult; token: string; checking: boolean; found: LiveOrderRow | null }
  | { state: "rejected"; message: string }
  | { state: "accepted"; order: LiveOrderRow };

const ORDER_POLL_MS = 10_000;

function OrdersView({ locale, state, safety }: { locale: Locale; state: LiveUiState; safety: TradingSafetyStatus | null }) {
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);
  const [orders, setOrders] = useState<LiveOrderRow[] | null>(null);
  const [fills, setFills] = useState<LiveFillRow[] | null>(null);
  const [fillsError, setFillsError] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
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
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const liveMandates = useMemo(() => (mandates || []).filter((mandate) => mandate.execution_mode === "live"), [mandates]);
  const selectedMandate = liveMandates.find((mandate) => mandate.id === mandateId) || null;
  const allowedSymbols = useMemo(() => selectedMandate?.allowed_symbols || [], [selectedMandate]);

  const load = useCallback(async () => {
    const results = await Promise.allSettled([getTradingMandates(), getLiveOrders(), getLiveFills()]);
    if (results[0].status === "fulfilled") {
      const list = (results[0].value.mandates || []).filter((mandate) => mandate.execution_mode === "live");
      setMandates(list);
      setMandateId((current) => current || list[0]?.id || "");
    }
    let latest: LiveOrderRow[] | null = null;
    if (results[1].status === "fulfilled") {
      latest = results[1].value.orders || [];
      setOrders(latest);
    }
    if (results[2].status === "fulfilled") {
      setFills(results[2].value.fills || []);
      setFillsError(false);
    } else {
      setFillsError(true);
    }
    setUpdatedAt(new Date().toISOString());
    return latest;
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Keep a symbol the mandate actually allows selected.
  useEffect(() => {
    if (allowedSymbols.length && !allowedSymbols.includes(symbol)) setSymbol(allowedSymbols[0]);
  }, [allowedSymbols, symbol]);

  const hasOpenOrders = (orders || []).some((order) => isOpenLiveOrderStatus(order.status));
  // Poll only while something can still change and the tab is visible.
  useEffect(() => {
    if (!hasOpenOrders) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, ORDER_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasOpenOrders, load]);

  // Countdown for the preview's validity window.
  useEffect(() => {
    if (!preview) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [preview]);

  const ambiguous = submission?.state === "ambiguous" || submission?.state === "submitting";

  const runPreview = async () => {
    setError("");
    setNotice("");
    setPreview(null);
    setRejection(null);
    setToken("");
    if (ambiguous || !mandateId || !symbol.trim() || !quantity.trim()) return;
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
      setSubmission(null);
      setNow(Date.now());
    } catch (cause) {
      if (cause instanceof LiveOrderRejectedError) {
        setRejection({ message: cause.message, status: cause.status, checks: cause.checks });
      } else {
        setError(t(locale, "live-trading.workflow.submission.unavailable"));
      }
    } finally {
      setBusy("");
    }
  };

  /** Look for the order an intent produced; the list is the server's truth. */
  const reconcile = async (intentId: string) => {
    setSubmission((current) => (current?.state === "ambiguous" ? { ...current, checking: true } : current));
    const latest = await load().catch(() => null);
    const found = (latest || []).find((order) => order.order_intent_id === intentId) || null;
    setSubmission((current) => (current?.state === "ambiguous" ? { ...current, checking: false, found } : current));
    return found;
  };

  const submit = async (target: LiveOrderPreviewResult, phrase: string) => {
    setBusy("confirm");
    setError("");
    setSubmission({ state: "submitting", preview: target, token: phrase });
    try {
      const { order } = await confirmLiveOrder(target.intent.id, phrase);
      setSubmission({ state: "accepted", order });
      setPreview(null);
      setToken("");
      setDialogOpen(false);
      setNotice(t(locale, "live-trading.orders.submitted"));
      await load();
    } catch (cause) {
      setDialogOpen(false);
      if (classifySubmitFailure(cause) === "rejected") {
        setSubmission({ state: "rejected", message: describeApiError(cause).message || t(locale, "live-trading.orders.confirmError") });
        setPreview(null);
        setToken("");
      } else {
        // No definite answer: keep the intent and phrase so the only retry
        // offered is the idempotent one, then reconcile against the list.
        setSubmission({ state: "ambiguous", preview: target, token: phrase, checking: true, found: null });
        const found = await reconcile(target.intent.id);
        if (found) {
          setSubmission({ state: "accepted", order: found });
          setPreview(null);
          setToken("");
        }
      }
    } finally {
      setBusy("");
    }
  };

  const discardIntent = () => {
    setPreview(null);
    setToken("");
    setDialogOpen(false);
    setNotice(t(locale, "live-trading.workflow.approval.denied"));
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
      setError(describeApiError(cause).message);
    } finally {
      setBusy("");
    }
  };

  const orderFormEnabled = state === "READY" && liveMandates.length > 0;
  const unknownOrders = (orders || []).filter((order) => isUnknownLiveOrderStatus(order.status));
  const remaining = preview ? secondsUntil(preview.intent.expires_at, now) : null;
  const previewExpired = remaining !== null && remaining <= 0;
  const notional = preview && preview.intent.order_type === "limit" ? multiplyDecimalStrings(preview.intent.quantity, preview.intent.limit_price) : null;
  const userCap = safety?.user_live_approval?.max_total_notional;

  return (
    <div className="space-y-5">
      {unknownOrders.length ? (
        <section role="alert" data-testid="live-unknown-banner" className="flex items-start gap-3 rounded-xl border border-status-warning bg-bg-panel p-4">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden />
          <p className="text-sm leading-6">{t(locale, "live-trading.workflow.unknown.banner", { count: unknownOrders.length })}</p>
        </section>
      ) : null}

      {submission?.state === "submitting" ? (
        <p role="status" className="flex items-center gap-2 text-sm text-text-pg-muted"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />{t(locale, "live-trading.workflow.submission.submitting")}</p>
      ) : null}

      {submission?.state === "ambiguous" ? (
        <section role="alert" data-testid="live-submission-ambiguous" className="rounded-xl border border-status-warning bg-bg-panel p-4">
          <h3 className="flex items-center gap-2 font-semibold text-status-warning"><AlertTriangle className="h-4 w-4" aria-hidden />{t(locale, "live-trading.workflow.submission.ambiguousTitle")}</h3>
          <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.workflow.submission.ambiguousBody")}</p>
          <p className="mt-2 font-mono text-xs text-text-pg-dim">{submission.preview.intent.side.toUpperCase()} {submission.preview.intent.quantity} {submission.preview.intent.symbol} · {t(locale, "live-trading.workflow.details.intent")} {submission.preview.intent.id.slice(0, 8)}</p>
          <p className="mt-2 text-xs" role="status">{submission.checking ? t(locale, "live-trading.workflow.submission.checking") : submission.found ? t(locale, "live-trading.workflow.submission.found", { client: submission.found.client_order_id, status: submission.found.status }) : t(locale, "live-trading.workflow.submission.notFound")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" disabled={submission.checking} onClick={() => void reconcile(submission.preview.intent.id)} className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border-pg px-3 text-sm hover:border-border-pg-strong disabled:opacity-40"><RefreshCw className="h-3.5 w-3.5" aria-hidden />{t(locale, "live-trading.workflow.submission.checkAgain")}</button>
            <button type="button" disabled={submission.checking || busy === "confirm"} onClick={() => void submit(submission.preview, submission.token)} className="min-h-10 rounded-lg border border-status-warning px-3 text-sm font-medium text-status-warning disabled:opacity-40">{t(locale, "live-trading.workflow.submission.resendSame")}</button>
            <button type="button" onClick={() => setSubmission(null)} className="min-h-10 rounded-lg px-3 text-xs text-text-pg-muted hover:text-text-pg">{t(locale, "live-trading.workflow.submission.clear")}</button>
          </div>
        </section>
      ) : null}

      {submission?.state === "rejected" ? (
        <section role="alert" data-testid="live-submission-rejected" className="rounded-xl border border-status-negative bg-bg-panel p-4">
          <h3 className="font-semibold text-status-negative">{t(locale, "live-trading.workflow.submission.rejectedTitle")}</h3>
          <p className="mt-1 text-sm text-text-pg-muted">{submission.message}</p>
        </section>
      ) : null}

      {submission?.state === "accepted" && isUnknownLiveOrderStatus(submission.order.status) ? (
        <p role="status" className="text-sm text-status-warning">{t(locale, "live-trading.workflow.unknown.row")}</p>
      ) : null}

      <section data-testid="live-order-form" className="rounded-xl border border-border-pg bg-bg-panel">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.orders.formTitle")}</h2></div>
        {!orderFormEnabled ? (
          <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.orders.noMandates")}</p>
        ) : (
          <div className="p-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.mandate")}
                <select value={mandateId} onChange={(event) => setMandateId(event.target.value)} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg">
                  {liveMandates.map((mandate) => <option key={mandate.id} value={mandate.id}>{mandate.id.slice(0, 8)} · {mandate.allowed_symbols?.join(",") || "—"}</option>)}
                </select>
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.symbol")}
                {allowedSymbols.length ? (
                  <select value={symbol} onChange={(event) => setSymbol(event.target.value)} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg">
                    {allowedSymbols.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                ) : (
                  <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} spellCheck={false} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg" />
                )}
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.side")}
                <select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg">
                  <option value="buy">{t(locale, "live-trading.orders.buy")}</option>
                  <option value="sell">{t(locale, "live-trading.orders.sell")}</option>
                </select>
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.orderType")}
                <select value={orderType} onChange={(event) => setOrderType(event.target.value as "market" | "limit")} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg">
                  <option value="market">{t(locale, "live-trading.orders.market")}</option>
                  <option value="limit">{t(locale, "live-trading.orders.limit")}</option>
                </select>
              </label>
              <label className="text-xs text-text-pg-muted">
                {t(locale, "live-trading.orders.quantity")}
                <input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="0.00000000" spellCheck={false} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg" />
              </label>
              {orderType === "limit" ? (
                <label className="text-xs text-text-pg-muted">
                  {t(locale, "live-trading.orders.limitPrice")}
                  <input inputMode="decimal" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} placeholder="0.00" spellCheck={false} className="mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm text-text-pg" />
                </label>
              ) : null}
            </div>
            <button type="button" onClick={() => void runPreview()} disabled={busy === "preview" || ambiguous} className="mt-4 inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border-pg px-4 text-sm font-medium hover:border-border-pg-strong disabled:opacity-40">
              {busy === "preview" ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : null}
              {busy === "preview" ? t(locale, "live-trading.orders.previewing") : t(locale, "live-trading.orders.preview")}
            </button>
            {ambiguous ? <p className="mt-2 text-xs text-status-warning">{t(locale, "live-trading.workflow.submission.previewBlocked")}</p> : null}
          </div>
        )}
      </section>

      {error ? <p className="text-sm text-status-negative" role="alert">{error}</p> : null}
      {notice ? <p className="text-sm text-status-positive" role="status">{notice}</p> : null}

      {rejection ? (
        <section data-testid="live-preview-rejection" className="rounded-xl border border-status-negative bg-bg-panel p-4" role="alert">
          <div className="flex items-start gap-3">
            <CircleX className="mt-0.5 h-5 w-5 shrink-0 text-status-negative" aria-hidden />
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold text-status-negative">{t(locale, "live-trading.orders.rejectedTitle")}</h3>
              <p className="mt-1 text-sm text-text-pg-muted">{rejection.message}</p>
              <p className="mt-1 text-xs text-status-warning">{t(locale, "live-trading.orders.rejectedHint")}</p>
            </div>
          </div>
          <div className="mt-4 overflow-x-auto rounded-lg border border-border-pg">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  <th className="p-2.5 font-medium">{t(locale, "live-trading.orders.riskChecks")}</th>
                  <th className="p-2.5 font-medium">{t(locale, "live-trading.states.liveDisabled.approvalStatus")}</th>
                  <th className="p-2.5 font-medium">{t(locale, "live-trading.workflow.details.show")}</th>
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

      {preview && !ambiguous ? (
        <section data-testid="live-order-approval" aria-labelledby="live-approval-title" className="rounded-xl border border-status-warning bg-bg-panel p-4">
          <h3 id="live-approval-title" className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4 text-status-warning" aria-hidden />{t(locale, "live-trading.workflow.approval.title")}</h3>
          <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
            <dt className="text-text-pg-muted">{t(locale, "live-trading.workflow.approval.action")}</dt>
            <dd className="font-mono" data-testid="approval-action">{preview.intent.side.toUpperCase()} {formatDecimalString(preview.intent.quantity)} {preview.intent.symbol} · {preview.intent.order_type}{preview.intent.limit_price ? ` @ ${formatDecimalString(preview.intent.limit_price)}` : ""}</dd>
            <dt className="text-text-pg-muted">{t(locale, "live-trading.workflow.approval.scope")}</dt>
            <dd className="break-words">{t(locale, "live-trading.workflow.approval.scopeValue", { mandate: preview.intent.mandate_id.slice(0, 8), symbols: (selectedMandate?.allowed_symbols || []).join(", ") || "—" })}</dd>
            <dt className="text-text-pg-muted">{t(locale, "live-trading.workflow.approval.impact")}</dt>
            <dd>{notional ? t(locale, "live-trading.workflow.approval.notionalLimit", { value: formatDecimalString(notional, 2), limit: formatDecimalString(selectedMandate?.max_per_order_notional, 2) || "—" }) : t(locale, "live-trading.workflow.approval.notionalMarket", { limit: formatDecimalString(selectedMandate?.max_per_order_notional, 2) || "—" })}</dd>
            <dt className="text-text-pg-muted">{t(locale, "live-trading.workflow.approval.permission")}</dt>
            <dd>{t(locale, "live-trading.workflow.approval.permissionValue", { approval: selectedMandate?.approval_status || "—", cap: userCap && userCap !== "0" ? formatDecimalString(userCap, 2) : "—" })}</dd>
            <dt className="text-text-pg-muted">{t(locale, "live-trading.workflow.approval.validity")}</dt>
            <dd data-testid="approval-validity" className={previewExpired ? "text-status-negative" : ""}>{previewExpired ? t(locale, "live-trading.workflow.approval.expired") : t(locale, "live-trading.workflow.approval.expiresIn", { seconds: Math.max(0, remaining ?? 0), time: new Date(preview.intent.expires_at).toLocaleTimeString(locale) })}</dd>
            <dt className="text-text-pg-muted">{t(locale, "live-trading.orders.traceId")}</dt>
            <dd className="min-w-0 truncate font-mono text-xs">{preview.trace_id}</dd>
          </dl>
          <p className="mt-3 text-xs text-text-pg-dim">{t(locale, "live-trading.workflow.approval.noRiskEstimate")}</p>
          <p className="mt-4 text-xs text-text-pg-muted">{t(locale, "live-trading.workflow.approval.typeToken")}</p>
          <code className="mt-2 block overflow-x-auto rounded-lg border border-border-pg bg-bg-panel-muted p-3 text-xs">{preview.confirmation}</code>
          <input value={token} onChange={(event) => setToken(event.target.value)} aria-label={t(locale, "live-trading.orders.confirmationInput")} placeholder={t(locale, "live-trading.orders.confirmationInput")} autoComplete="off" spellCheck={false} disabled={previewExpired} className="mt-3 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm disabled:opacity-50" />
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={() => setDialogOpen(true)} disabled={!token.trim() || busy === "confirm" || previewExpired} className="min-h-10 rounded-lg border border-status-warning px-4 text-sm font-semibold text-status-warning disabled:opacity-40">
              {t(locale, "live-trading.workflow.approval.approve")}
            </button>
            <button type="button" onClick={discardIntent} className="min-h-10 rounded-lg border border-border-pg px-4 text-sm hover:border-border-pg-strong">{t(locale, "live-trading.workflow.approval.deny")}</button>
          </div>
        </section>
      ) : null}

      {dialogOpen && preview ? (
        <ConfirmOrderDialog
          locale={locale}
          preview={preview}
          busy={busy === "confirm"}
          onBack={() => setDialogOpen(false)}
          onConfirm={() => void submit(preview, token.trim())}
        />
      ) : null}

      <section className="rounded-xl border border-border-pg bg-bg-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-pg p-4">
          <h2 className="font-semibold">{t(locale, "live-trading.orders.listTitle")}</h2>
          <div className="flex items-center gap-2 text-xs text-text-pg-dim">
            {hasOpenOrders ? <span>{t(locale, "live-trading.workflow.refresh.auto")}</span> : null}
            {updatedAt ? <span>{t(locale, "live-trading.workflow.refresh.updated", { time: new Date(updatedAt).toLocaleTimeString(locale) })}</span> : null}
            <button type="button" onClick={() => void load()} aria-label={t(locale, "live-trading.workflow.refresh.now")} className="grid h-9 w-9 place-items-center rounded-lg border border-border-pg hover:border-border-pg-strong"><RefreshCw className="h-3.5 w-3.5" aria-hidden /></button>
          </div>
        </div>
        {orders === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
        {orders !== null && orders.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.orders.empty")}</p> : null}
        {orders !== null && orders.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  {[t(locale, "live-trading.orders.colCreated"), t(locale, "live-trading.orders.colSymbol"), t(locale, "live-trading.orders.colSide"), t(locale, "live-trading.orders.colQuantity"), t(locale, "live-trading.orders.colType"), t(locale, "live-trading.orders.colStatus"), t(locale, "live-trading.orders.colFilled"), t(locale, "live-trading.orders.colClientOrderId"), t(locale, "live-trading.orders.colActions")].map((head) => <th key={head} className="p-2.5 font-medium">{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => <OrderRow key={order.id} order={order} locale={locale} onCancel={() => setCancelTarget(order)} onSynced={() => void load()} />)}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="rounded-xl border border-border-pg bg-bg-panel">
        <div className="border-b border-border-pg p-4"><h3 className="font-semibold">{t(locale, "live-trading.orders.fillsTitle")}</h3></div>
        {fillsError ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.workflow.fills.unavailable")}</p> : null}
        {!fillsError && fills === null ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
        {!fillsError && fills !== null && fills.length === 0 ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.workflow.fills.empty")}</p> : null}
        {!fillsError && fills && fills.length > 0 ? (
          <div className="overflow-x-auto" data-testid="live-fills">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  {[t(locale, "live-trading.workflow.fills.colTime"), t(locale, "live-trading.orders.colSymbol"), t(locale, "live-trading.orders.colSide"), t(locale, "live-trading.orders.colQuantity"), t(locale, "live-trading.workflow.fills.colPrice"), t(locale, "live-trading.workflow.fills.colFee")].map((head) => <th key={head} className="p-2.5 font-medium">{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {fills.map((fill) => (
                  <tr key={fill.id} className="border-b border-border-pg last:border-0">
                    <td className="p-2.5 text-xs text-text-pg-muted">{fill.executed_at ? new Date(fill.executed_at).toLocaleString(locale) : t(locale, "live-trading.common.noValue")}</td>
                    <td className="p-2.5 font-mono text-xs font-semibold">{fill.symbol}</td>
                    <td className="p-2.5 text-xs">{fill.side}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(fill.quantity)}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(fill.price)}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(fill.fee)} {fill.fee_currency || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {cancelTarget ? (
        <CancelOrderDialog locale={locale} order={cancelTarget} busy={busy === `cancel:${cancelTarget.client_order_id}`} onBack={() => setCancelTarget(null)} onConfirm={() => void runCancel(cancelTarget)} />
      ) : null}
    </div>
  );
}

function OrderRow({ order, locale, onCancel, onSynced }: { order: LiveOrderRow; locale: Locale; onCancel: () => void; onSynced?: () => void }) {
  const unknown = isUnknownLiveOrderStatus(order.status);
  return (
    <>
      <tr className={`align-top ${unknown ? "bg-[var(--pg-warning-soft,transparent)]" : ""} ${unknown || order.error_code ? "" : "border-b border-border-pg last:border-0"}`} data-testid={unknown ? "live-order-unknown" : undefined}>
        <td className="p-2.5 text-xs text-text-pg-muted">{new Date(order.created_at).toLocaleString(locale)}</td>
        <td className="p-2.5 font-mono text-xs font-semibold">{order.symbol}</td>
        <td className="p-2.5 text-xs">{order.side}</td>
        <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(order.quantity)}</td>
        <td className="p-2.5 text-xs">{order.order_type}{order.limit_price ? ` @ ${formatDecimalString(order.limit_price)}` : ""}</td>
        <td className="p-2.5"><OrderStatusBadge status={order.status} locale={locale} /></td>
        <td className="p-2.5 font-mono text-xs tabular-nums">{formatDecimalString(order.filled_quantity)}</td>
        <td className="p-2.5 font-mono text-xs text-text-pg-muted">{order.client_order_id}</td>
        <td className="p-2.5">
          {isOpenLiveOrderStatus(order.status) ? (
            <button type="button" onClick={onCancel} className="min-h-9 rounded-lg border border-border-pg px-2 text-xs text-status-warning hover:border-border-pg-strong">{t(locale, "live-trading.orders.cancel")}</button>
          ) : null}
        </td>
      </tr>
      <tr className="border-b border-border-pg last:border-0">
        <td colSpan={9} className="px-2.5 pb-2.5 pt-0">
          {unknown ? <p className="mb-1 text-xs text-status-warning">{t(locale, "live-trading.workflow.unknown.row")} · {order.last_sync_at ? t(locale, "live-trading.workflow.unknown.lastSync", { time: new Date(order.last_sync_at).toLocaleString(locale) }) : t(locale, "live-trading.workflow.unknown.neverSynced")}</p> : null}
          {unknown ? <OrderSyncPanel locale={locale} orderId={order.id} onChanged={onSynced} /> : null}
          <details className="text-xs text-text-pg-muted">
            <summary className="cursor-pointer select-none rounded py-0.5 hover:text-text-pg">{t(locale, "live-trading.workflow.details.show")}</summary>
            <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
              <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.orders.colBrokerOrderId")}</dt><dd className="font-mono">{order.broker_order_id || t(locale, "live-trading.common.noValue")}</dd></div>
              <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.workflow.details.averagePrice")}</dt><dd className="font-mono">{order.average_price ? formatDecimalString(order.average_price) : t(locale, "live-trading.common.noValue")}</dd></div>
              <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.workflow.details.submittedAt")}</dt><dd>{order.submitted_at ? new Date(order.submitted_at).toLocaleString(locale) : t(locale, "live-trading.common.noValue")}</dd></div>
              <div className="flex justify-between gap-3"><dt>{t(locale, "live-trading.workflow.details.lastSync")}</dt><dd>{order.last_sync_at ? new Date(order.last_sync_at).toLocaleString(locale) : t(locale, "live-trading.common.noValue")}</dd></div>
              {order.error_code ? <div className="flex justify-between gap-3 sm:col-span-2"><dt>{t(locale, "live-trading.workflow.details.error")}</dt><dd className="min-w-0 break-words text-right"><span className="font-mono">{order.error_code}</span>{order.error_message ? ` · ${order.error_message}` : ""}</dd></div> : null}
              {order.trace_id ? <div className="flex justify-between gap-3 sm:col-span-2"><dt>{t(locale, "live-trading.workflow.details.trace")}</dt><dd className="min-w-0 truncate font-mono">{order.trace_id}</dd></div> : null}
            </dl>
          </details>
        </td>
      </tr>
    </>
  );
}

/**
 * What the server last heard from the venue about an UNKNOWN order, and a
 * query-only "ask again". The button never places, re-sends or changes an
 * order; it is rate-limited per order by the server, which also decides
 * whether it is offered at all.
 */
function OrderSyncPanel({ locale, orderId, onChanged }: { locale: Locale; orderId: string; onChanged?: () => void }) {
  const [sync, setSync] = useState<LiveOrderSyncStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const read = useCallback(async () => {
    try {
      setSync((await getLiveOrderSyncStatus(orderId)).sync);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [orderId]);
  useEffect(() => { void read(); }, [read]);

  const recheck = async () => {
    setBusy(true);
    setMessage("");
    try {
      const result = (await recheckLiveOrder(orderId)).sync;
      setSync(result);
      setMessage(t(locale, "live-trading.workflow.sync.asked"));
      if (result.status !== "unknown") onChanged?.();
    } catch (error) {
      const { status, message: detail } = describeApiError(error);
      setMessage(status === 429 ? t(locale, "live-trading.workflow.sync.rateLimited") : status === 403 ? t(locale, "live-trading.workflow.sync.disabled") : detail || t(locale, "live-trading.workflow.sync.failed"));
      await read();
    } finally {
      setBusy(false);
    }
  };

  if (failed) return <p className="mb-1 text-xs text-text-pg-muted" data-testid="live-order-sync-unavailable">{t(locale, "live-trading.workflow.sync.unavailable")}</p>;
  if (!sync) return null;
  const latest = sync.latest;
  const outcomeKey = `live-trading.workflow.sync.outcome.${latest?.outcome ?? "none"}` as TranslationKey;
  const blocked = sync.recheck.blocked_reason;
  return (
    <div className="mb-2 rounded-lg border border-border-pg px-3 py-2 text-xs" data-testid="live-order-sync">
      <p>
        <span className="text-text-pg-muted">{t(locale, "live-trading.workflow.sync.lastAsked")}: </span>
        <span>{sync.last_sync_at ? new Date(sync.last_sync_at).toLocaleString(locale) : t(locale, "live-trading.workflow.unknown.neverSynced")}</span>
      </p>
      <p className="mt-0.5" data-testid="live-order-sync-latest">
        <span className="text-text-pg-muted">{t(locale, "live-trading.workflow.sync.answer")}: </span>
        {latest ? <>{hasTranslation(locale, outcomeKey) ? t(locale, outcomeKey) : latest.outcome}{latest.reason ? <span className="text-text-pg-dim"> · {latest.reason}</span> : null}{latest.at ? <span className="text-text-pg-dim"> · {new Date(latest.at).toLocaleString(locale)}</span> : null}</> : t(locale, "live-trading.workflow.sync.outcome.none")}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {sync.recheck.enabled ? (
          <button type="button" onClick={() => void recheck()} disabled={busy || !sync.recheck.allowed} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border-pg px-3 hover:border-border-pg-strong disabled:opacity-40" data-testid="live-order-recheck">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />{t(locale, "live-trading.workflow.sync.recheck")}
          </button>
        ) : null}
        <span className="text-text-pg-dim">
          {blocked === "disabled" ? t(locale, "live-trading.workflow.sync.disabled") : blocked === "rate_limited" && sync.recheck.next_allowed_at ? t(locale, "live-trading.workflow.sync.nextAt", { time: new Date(sync.recheck.next_allowed_at).toLocaleTimeString(locale) }) : t(locale, "live-trading.workflow.sync.queryOnly")}
        </span>
      </div>
      {message ? <p role="status" className="mt-1 text-text-pg-muted">{message}</p> : null}
    </div>
  );
}

function ConfirmOrderDialog({ locale, preview, busy, onBack, onConfirm }: { locale: Locale; preview: LiveOrderPreviewResult; busy: boolean; onBack: () => void; onConfirm: () => void }) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backRef = useRef<HTMLButtonElement | null>(null);
  useDialogFocus(true, panelRef, onBack, backRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="live-confirm-title" className="w-full max-w-md rounded-xl border border-status-warning bg-bg-panel p-5">
        <h3 id="live-confirm-title" className="font-semibold text-status-warning">{t(locale, "live-trading.orders.confirmDialogTitle")}</h3>
        <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.orders.confirmDialogBody")}</p>
        <dl className="mt-4 space-y-2 rounded-lg border border-border-pg bg-bg-panel-muted p-3 text-sm">
          <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogSymbol")}</dt><dd className="font-mono">{preview.intent.symbol}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogSide")}</dt><dd>{preview.intent.side}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogQuantity")}</dt><dd className="font-mono tabular-nums">{formatDecimalString(preview.intent.quantity)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogType")}</dt><dd>{preview.intent.order_type}</dd></div>
          {preview.intent.limit_price ? <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogLimitPrice")}</dt><dd className="font-mono tabular-nums">{formatDecimalString(preview.intent.limit_price)}</dd></div> : null}
          <div className="flex justify-between gap-3"><dt className="text-text-pg-muted">{t(locale, "live-trading.orders.dialogVenue")}</dt><dd>{t(locale, "live-trading.orders.dialogVenueValue")}</dd></div>
        </dl>
        <div className="mt-4 flex gap-2">
          <button ref={backRef} type="button" onClick={onBack} className="min-h-10 flex-1 rounded-lg border border-border-pg px-3 text-sm">{t(locale, "live-trading.orders.dialogBack")}</button>
          <button type="button" onClick={onConfirm} disabled={busy} className="min-h-10 flex-1 rounded-lg border border-status-warning px-3 text-sm font-semibold text-status-warning disabled:opacity-40">
            {busy ? <Loader2 className="mx-auto h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : t(locale, "live-trading.orders.dialogConfirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

function CancelOrderDialog({ locale, order, busy, onBack, onConfirm }: { locale: Locale; order: LiveOrderRow; busy: boolean; onBack: () => void; onConfirm: () => void }) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backRef = useRef<HTMLButtonElement | null>(null);
  useDialogFocus(true, panelRef, onBack, backRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="live-cancel-title" className="w-full max-w-md rounded-xl border border-status-warning bg-bg-panel p-5">
        <h3 id="live-cancel-title" className="font-semibold text-status-warning">{t(locale, "live-trading.orders.cancelConfirmTitle")}</h3>
        <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.orders.cancelConfirmBody")}</p>
        <p className="mt-3 break-all font-mono text-xs text-text-pg-muted">{order.symbol} · {order.side} · {formatDecimalString(order.quantity)} · {order.client_order_id}</p>
        <div className="mt-4 flex gap-2">
          <button ref={backRef} type="button" onClick={onBack} className="min-h-10 flex-1 rounded-lg border border-border-pg px-3 text-sm">{t(locale, "live-trading.orders.dialogBack")}</button>
          <button type="button" onClick={onConfirm} disabled={busy} className="min-h-10 flex-1 rounded-lg border border-status-warning px-3 text-sm font-semibold text-status-warning disabled:opacity-40">{t(locale, "live-trading.orders.cancel")}</button>
        </div>
      </div>
    </div>
  );
}

function OrderStatusBadge({ status, locale }: { status: string; locale: Locale }) {
  const normalized = (status || "").toLowerCase();
  const tone = normalized === "filled" ? "text-status-positive" : normalized === "partially_filled" || normalized === "pending" || normalized === "accepted" || normalized === "submitted" ? "text-text-pg" : normalized === "unknown" ? "text-status-warning" : normalized === "rejected" ? "text-status-negative" : "text-text-pg-dim";
  void locale;
  return <span className={`inline-flex items-center gap-1 rounded-md border border-border-pg bg-bg-panel-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tone}`}>{normalized === "unknown" ? <CircleAlert className="h-3 w-3" aria-hidden /> : null}{status}</span>;
}

// ── Account view ──────────────────────────────────────────────────────────

function AccountView({ locale, safety, onReload }: { locale: Locale; safety: TradingSafetyStatus | null; onReload: () => void }) {
  const [navLoad, setNavLoad] = useState<NavLoad>({ kind: "loading" });
  const [positions, setPositions] = useState<Array<{ symbol: string; quantity: string; mark_price: string | null; market_value: string | null; price_timestamp?: string | null; stale: boolean }> | null>(null);
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);

  const reloadMandates = useCallback(async () => {
    const mandateResult = await getTradingMandates().catch(() => null);
    if (mandateResult) setMandates((mandateResult.mandates || []).filter((mandate) => mandate.execution_mode === "live"));
  }, []);
  useEffect(() => {
    void (async () => {
      const [navResult, positionResult] = await Promise.all([loadNav(), getLivePortfolioPositions().catch(() => null)]);
      setNavLoad(navResult);
      if (positionResult) setPositions(positionResult.positions || []);
      await reloadMandates();
    })();
  }, [reloadMandates]);

  const liveMandates = mandates || [];

  return (
    <div className="space-y-5">
      <section className="border border-border-pg bg-bg-panel rounded-xl">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.account.balances")}</h2></div>
        <div className="p-4">
          <NavPanel locale={locale} load={navLoad} extra={(nav) => [{ label: t(locale, "live-trading.account.reconciliation"), value: reconciliationLabel(nav.reconciliation_status, locale) }]} />
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
                    <td className="p-2.5 font-mono text-xs tabular-nums">{position.mark_price == null ? <span className="text-status-warning">{t(locale, "live-trading.workflow.nav.noPrice")}</span> : formatDecimalString(position.mark_price)}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{position.market_value == null ? t(locale, "live-trading.common.noValue") : formatDecimalString(position.market_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <ReconciliationSection locale={locale} />

      <LedgerSection locale={locale} />

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
              <MandateGateList locale={locale} gate={safety?.mandates?.[mandate.id]} />
              {mandate.paused ? <div className="mt-3"><ResumeMandate locale={locale} mandate={mandate} killSwitchEngaged={(safety?.kill_switches || []).length > 0} onDone={() => { void reloadMandates(); onReload(); }} /></div> : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ── Ledger + reconciliation (owner-scoped, read-only) ─────────────────────

type ReadFailure = "no-account" | "unavailable";

function readFailure(error: unknown): ReadFailure {
  const { status, code } = describeApiError(error);
  return status === 404 && code === "TRADING_ACCOUNT_NOT_FOUND" ? "no-account" : "unavailable";
}

type LedgerLoad =
  | { kind: "loading" }
  | { kind: "failed"; reason: ReadFailure }
  | { kind: "ready"; entries: LiveLedgerEntry[]; nextCursor: string | null; more: "idle" | "loading" | "failed" };

const LEDGER_PAGE_SIZE = 50;

/**
 * The caller's append-only ledger, newest first. "No account", "could not be
 * read" and "no rows yet" are three different statements and never render as
 * a zero; older pages are fetched with the server's keyset cursor.
 */
function LedgerSection({ locale }: { locale: Locale }) {
  const [load, setLoad] = useState<LedgerLoad>({ kind: "loading" });

  const firstPage = useCallback(async () => {
    setLoad({ kind: "loading" });
    try {
      const page = await getLiveLedger({ limit: LEDGER_PAGE_SIZE });
      setLoad({ kind: "ready", entries: page.entries || [], nextCursor: page.next_cursor, more: "idle" });
    } catch (error) {
      setLoad({ kind: "failed", reason: readFailure(error) });
    }
  }, []);
  useEffect(() => { void firstPage(); }, [firstPage]);

  const loadMore = async () => {
    if (load.kind !== "ready" || !load.nextCursor || load.more === "loading") return;
    const cursor = load.nextCursor;
    setLoad({ ...load, more: "loading" });
    try {
      const page = await getLiveLedger({ cursor, limit: LEDGER_PAGE_SIZE });
      setLoad((current) => current.kind === "ready" ? { kind: "ready", entries: [...current.entries, ...(page.entries || [])], nextCursor: page.next_cursor, more: "idle" } : current);
    } catch {
      // Keep what is already shown; only the next page failed.
      setLoad((current) => current.kind === "ready" ? { ...current, more: "failed" } : current);
    }
  };

  const none = t(locale, "live-trading.common.noValue");
  return (
    <section className="rounded-xl border border-border-pg bg-bg-panel" data-testid="live-ledger">
      <div className="border-b border-border-pg p-4">
        <h2 className="font-semibold">{t(locale, "live-trading.account.ledger")}</h2>
        <p className="mt-1 text-xs text-text-pg-dim">{t(locale, "live-trading.account.ledgerNote")}</p>
      </div>
      {load.kind === "loading" ? <p className="p-4 text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
      {load.kind === "failed" ? (
        <div className="flex flex-wrap items-center gap-3 p-4" role="status" data-testid={load.reason === "no-account" ? "live-ledger-no-account" : "live-ledger-unavailable"}>
          <p className="text-sm text-text-pg-muted">{t(locale, load.reason === "no-account" ? "live-trading.account.ledgerNoAccount" : "live-trading.account.ledgerUnavailable")}</p>
          {load.reason === "unavailable" ? <button type="button" onClick={() => void firstPage()} className="min-h-9 rounded-lg border border-border-pg px-3 text-xs hover:border-border-pg-strong">{t(locale, "live-trading.common.retry")}</button> : null}
        </div>
      ) : null}
      {load.kind === "ready" && load.entries.length === 0 ? <p className="p-4 text-sm text-text-pg-muted" data-testid="live-ledger-empty">{t(locale, "live-trading.account.ledgerEmpty")}</p> : null}
      {load.kind === "ready" && load.entries.length > 0 ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <caption className="sr-only">{t(locale, "live-trading.account.ledger")}</caption>
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">
                  {[t(locale, "live-trading.account.ledgerColTime"), t(locale, "live-trading.account.ledgerColType"), t(locale, "live-trading.account.colSymbol"), t(locale, "live-trading.account.colQuantity"), t(locale, "live-trading.account.ledgerColPrice"), t(locale, "live-trading.account.ledgerColAmount"), t(locale, "live-trading.account.ledgerColBalance"), t(locale, "live-trading.account.ledgerColRef")].map((head) => <th key={head} scope="col" className="p-2.5 font-medium">{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {load.entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-border-pg last:border-0" data-testid="live-ledger-row">
                    <td className="p-2.5 text-xs text-text-pg-muted">{new Date(entry.created_at).toLocaleString(locale)}</td>
                    <td className="p-2.5 font-mono text-xs">{entry.entry_type}</td>
                    <td className="p-2.5 font-mono text-xs">{entry.symbol || none}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{entry.quantity == null ? none : formatDecimalString(entry.quantity)}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{entry.price == null ? none : formatDecimalString(entry.price)}</td>
                    <td className={`p-2.5 font-mono text-xs tabular-nums ${entry.amount.startsWith("-") ? "text-status-negative" : ""}`}>{formatDecimalString(entry.amount)} {entry.currency}</td>
                    <td className="p-2.5 font-mono text-xs tabular-nums">{entry.balance_after == null ? <span className="text-text-pg-dim">{t(locale, "live-trading.account.ledgerNotRecorded")}</span> : formatDecimalString(entry.balance_after)}</td>
                    <td className="max-w-[12rem] truncate p-2.5 font-mono text-xs text-text-pg-dim">{entry.ref_type ? `${entry.ref_type}:${(entry.ref_id || "").slice(0, 8)}` : none}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-border-pg p-3 text-xs text-text-pg-muted">
            <span>{t(locale, "live-trading.account.ledgerShown", { count: load.entries.length })}</span>
            {load.nextCursor ? (
              <button type="button" onClick={() => void loadMore()} disabled={load.more === "loading"} className="min-h-9 rounded-lg border border-border-pg px-3 hover:border-border-pg-strong disabled:opacity-40" data-testid="live-ledger-more">
                {load.more === "loading" ? t(locale, "live-trading.common.loading") : t(locale, "live-trading.account.ledgerMore")}
              </button>
            ) : <span data-testid="live-ledger-end">{t(locale, "live-trading.account.ledgerEnd")}</span>}
            {load.more === "failed" ? <span role="alert" className="text-status-warning">{t(locale, "live-trading.account.ledgerMoreFailed")}</span> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

type ReconciliationLoad = { kind: "loading" } | { kind: "failed"; reason: ReadFailure } | { kind: "ready"; view: LiveReconciliationView };

/**
 * Ledger-derived balances beside the latest exchange reconciliation. Balances
 * are per currency (a BTC fee is not USD cash). "Never reconciled" means the
 * comparison is unavailable, which is not the same as "no differences".
 */
function ReconciliationSection({ locale }: { locale: Locale }) {
  const [load, setLoad] = useState<ReconciliationLoad>({ kind: "loading" });
  const read = useCallback(async () => {
    setLoad({ kind: "loading" });
    try {
      setLoad({ kind: "ready", view: await getLiveReconciliation() });
    } catch (error) {
      setLoad({ kind: "failed", reason: readFailure(error) });
    }
  }, []);
  useEffect(() => { void read(); }, [read]);

  const none = t(locale, "live-trading.common.noValue");
  const amount = (value: string | null | undefined) => (value == null ? none : formatDecimalString(value));
  return (
    <section className="rounded-xl border border-border-pg bg-bg-panel" data-testid="live-reconciliation">
      <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{t(locale, "live-trading.account.reconTitle")}</h2></div>
      <div className="space-y-4 p-4">
        {load.kind === "loading" ? <p className="text-sm text-text-pg-muted">{t(locale, "live-trading.common.loading")}</p> : null}
        {load.kind === "failed" ? (
          <div className="flex flex-wrap items-center gap-3" role="status" data-testid={load.reason === "no-account" ? "live-recon-no-account" : "live-recon-unavailable"}>
            <p className="text-sm text-text-pg-muted">{t(locale, load.reason === "no-account" ? "live-trading.account.ledgerNoAccount" : "live-trading.account.reconUnavailable")}</p>
            {load.reason === "unavailable" ? <button type="button" onClick={() => void read()} className="min-h-9 rounded-lg border border-border-pg px-3 text-xs hover:border-border-pg-strong">{t(locale, "live-trading.common.retry")}</button> : null}
          </div>
        ) : null}
        {load.kind === "ready" ? (
          <>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-text-pg-muted">{t(locale, "live-trading.account.reconLedgerBalances")}</h3>
              {load.view.ledger.empty ? (
                <p className="mt-1 text-sm text-text-pg-muted" data-testid="live-recon-ledger-empty">{t(locale, "live-trading.account.ledgerEmpty")}</p>
              ) : (
                <ul className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-sm" data-testid="live-recon-balances">
                  {load.view.ledger.balances.map((row) => <li key={row.currency} className="font-mono tabular-nums">{formatDecimalString(row.amount)} {row.currency}</li>)}
                </ul>
              )}
            </div>
            {load.view.latest ? (
              <div data-testid="live-recon-latest">
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <span className={load.view.latest.status === "ok" ? "text-status-positive" : "font-semibold text-status-warning"}>{reconStatusLabel(load.view.latest.status, locale)}</span>
                  <span className="text-xs text-text-pg-dim">{t(locale, "live-trading.account.reconAt", { time: new Date(load.view.latest.created_at).toLocaleString(locale) })}</span>
                  {load.view.latest.reviewed ? <span className="text-xs text-text-pg-muted">· {t(locale, "live-trading.account.reconReviewed", { time: new Date(load.view.latest.reviewed.reviewed_at).toLocaleString(locale) })}</span> : null}
                </p>
                <div className="mt-3 grid gap-px overflow-hidden rounded-lg border border-border-pg bg-border-pg sm:grid-cols-3">
                  <Field label={t(locale, "live-trading.account.reconExchange")} value={amount(load.view.latest.exchange_balance.cash)} />
                  <Field label={t(locale, "live-trading.account.reconLedger")} value={amount(load.view.latest.ledger_balance.cash)} />
                  <Field label={t(locale, "live-trading.account.reconNav")} value={amount(load.view.latest.nav.cash)} />
                </div>
                {load.view.latest.differences.length ? (
                  <ul className="mt-3 space-y-1 text-xs" data-testid="live-recon-differences">
                    {load.view.latest.differences.map((difference, index) => (
                      <li key={index} className="rounded-lg border border-status-warning px-3 py-2">
                        <span className="font-mono">{difference.source || none}</span>
                        {difference.delta != null ? <span className="ml-2 font-mono tabular-nums">Δ {formatDecimalString(difference.delta)}</span> : null}
                        {difference.detail ? <span className="ml-2 text-text-pg-muted">{difference.detail}</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {load.view.latest.status !== "ok" ? <p className="mt-2 text-xs text-text-pg-muted">{t(locale, "live-trading.account.reconAdminOnly")}</p> : null}
              </div>
            ) : (
              <p className="text-sm text-text-pg-muted" data-testid="live-recon-never">{t(locale, "live-trading.account.reconNever")}</p>
            )}
          </>
        ) : null}
      </div>
    </section>
  );
}

function reconStatusLabel(status: string, locale: Locale): string {
  const key = `live-trading.account.reconStatus.${status}` as TranslationKey;
  return hasTranslation(locale, key) ? t(locale, key) : status;
}

function reconciliationLabel(status: string, locale: Locale): string {
  const zh = locale === "zh";
  if (status === "ok") return zh ? "正常" : "ok";
  if (status === "pending") return zh ? "待处理" : "pending";
  if (status === "mismatch") return zh ? "存在差异（已暂停 Mandate）" : "mismatch (mandate paused)";
  return status || t(locale, "live-trading.common.noValue");
}

type MandateGate = TradingSafetyStatus["mandates"][string];

/**
 * Why a mandate cannot trade, from the server's own gate evaluation. Only
 * failing checks are listed (with the server's detail); a passing mandate
 * says how many checks passed. The browser never decides eligibility.
 */
function MandateGateList({ locale, gate }: { locale: Locale; gate: MandateGate | undefined }) {
  if (!gate) return <p className="mt-2 text-xs text-text-pg-dim">{t(locale, "live-trading.workflow.gates.unknown")}</p>;
  const entries = Object.entries(gate.checks || {});
  const failing = entries.filter(([, check]) => !check.ok);
  if (!failing.length) return <p className="mt-2 text-xs text-status-positive" data-testid="mandate-gates-pass">{t(locale, "live-trading.workflow.gates.allPass", { count: entries.length })}</p>;
  return (
    <div className="mt-3 rounded-lg border border-status-warning px-3 py-2" data-testid="mandate-gates-failing">
      <p className="text-xs font-semibold text-status-warning">{t(locale, "live-trading.workflow.gates.title")}</p>
      <ul className="mt-1 space-y-0.5 text-xs">
        {failing.map(([name, check]) => {
          const key = `live-trading.workflow.gates.labels.${name}` as TranslationKey;
          const label = hasTranslation(locale, key) ? t(locale, key) : name;
          const detail = check.detail === undefined || check.detail === "" || check.detail === false ? "" : String(check.detail);
          return <li key={name} className="flex flex-wrap gap-x-2"><span>{label}</span>{detail ? <span className="font-mono text-text-pg-dim">{detail}</span> : null}</li>;
        })}
      </ul>
    </div>
  );
}

/**
 * Resume a paused mandate. The server requires the exact phrase
 * `RESUME <mandate id>`, refuses reconciliation- or kill-switch-triggered
 * pauses, and re-checks every gate; this dialog states all of that up front
 * and shows the server's answer verbatim when it refuses.
 */
function ResumeMandate({ locale, mandate, killSwitchEngaged, onDone }: { locale: Locale; mandate: TradingMandate; killSwitchEngaged: boolean; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backRef = useRef<HTMLButtonElement | null>(null);
  const close = useCallback(() => setOpen(false), []);
  useDialogFocus(open, panelRef, close, backRef);
  const expected = `RESUME ${mandate.id}`;
  const reconciliation = (mandate.pause_reason || "").startsWith("reconciliation");
  const blockedReason = reconciliation ? t(locale, "live-trading.workflow.resume.reconciliation") : killSwitchEngaged ? t(locale, "live-trading.workflow.resume.killSwitch") : "";
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await resumeTradingMandate(mandate.id, phrase.trim());
      setOpen(false);
      onDone();
    } catch (cause) {
      setError(describeApiError(cause).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); setPhrase(""); setError(""); }} className="min-h-9 rounded-lg border border-border-pg px-3 text-xs hover:border-border-pg-strong" data-testid={`resume-mandate-${mandate.id}`}>{t(locale, "live-trading.workflow.resume.button")}</button>
      {open ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={`resume-title-${mandate.id}`} className="w-full max-w-md rounded-xl border border-status-warning bg-bg-panel p-5">
            <h3 id={`resume-title-${mandate.id}`} className="font-semibold text-status-warning">{t(locale, "live-trading.workflow.resume.title")}</h3>
            <p className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "live-trading.workflow.resume.body")}</p>
            {mandate.pause_reason ? <p className="mt-2 text-xs text-text-pg-dim">{t(locale, "live-trading.workflow.resume.reason")}: {mandate.pause_reason}</p> : null}
            {blockedReason ? <p role="status" className="mt-3 text-sm text-status-warning">{blockedReason}</p> : (
              <>
                <p className="mt-3 text-xs text-text-pg-muted">{t(locale, "live-trading.workflow.resume.typePhrase")}</p>
                <code className="mt-1 block break-all rounded-lg border border-border-pg bg-bg-panel-muted p-2 text-xs">{expected}</code>
                <input value={phrase} onChange={(event) => setPhrase(event.target.value)} aria-label={t(locale, "live-trading.workflow.resume.typePhrase")} autoComplete="off" spellCheck={false} className="mt-2 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 font-mono text-sm" />
              </>
            )}
            {error ? <p role="alert" className="mt-2 text-sm text-status-negative">{error}</p> : null}
            <div className="mt-4 flex gap-2">
              <button ref={backRef} type="button" onClick={close} className="min-h-10 flex-1 rounded-lg border border-border-pg px-3 text-sm">{t(locale, "live-trading.orders.dialogBack")}</button>
              {blockedReason ? null : <button type="button" onClick={() => void submit()} disabled={busy || phrase.trim() !== expected} className="min-h-10 flex-1 rounded-lg border border-status-warning px-3 text-sm font-semibold text-status-warning disabled:opacity-40">{t(locale, "live-trading.workflow.resume.confirm")}</button>}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-panel p-3">
      <p className="text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</p>
      <p className="mt-1 break-words text-sm font-medium tabular-nums text-text-pg">{value}</p>
    </div>
  );
}
