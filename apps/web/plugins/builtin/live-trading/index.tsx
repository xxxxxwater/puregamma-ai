import type { Context } from "cordis";
import { isLocale } from "@/i18n/routing";
import type { FrontendPlugin } from "@/plugins/core/contracts";
import {
  getTradingMandates,
  pauseTradingMandate,
  type TradingSafetyStatus,
} from "@/lib/api";
import { deriveLiveUiState } from "./state";

export const id = "puregamma.live-trading";
export const version = "1.0.0";
export const permissions = ["read:portfolio", "trade:live"] as const;

type LiveConsoleView = "overview" | "connect" | "orders" | "account";

const ROUTES: Record<LiveConsoleView, string> = {
  overview: "/trading/live",
  connect: "/trading/live/connect",
  orders: "/trading/live/orders",
  account: "/trading/live/account",
};

const PANEL_TITLES: Record<LiveConsoleView, string> = {
  overview: "LIVE Trading",
  connect: "LIVE Trading — Connect",
  orders: "LIVE Trading — Orders",
  account: "LIVE Trading — Account",
};

function loadConsole(view: LiveConsoleView) {
  return () =>
    import("@/components/live-trading-console").then((module) => ({
      default: ({ locale = "en" }: { locale?: string }) => (
        <module.LiveTradingConsole locale={isLocale(locale) ? locale : "en"} view={view} />
      ),
    }));
}

/**
 * Emergency pause: pause every non-paused LIVE mandate the user owns.
 * Pausing is always the conservative direction (it blocks new orders), so
 * the programmatic command may run without an interactive dialog; the
 * on-screen button in the console adds the required two-step confirmation.
 */
async function emergencyPauseAllLiveMandates(): Promise<boolean> {
  try {
    const { mandates } = await getTradingMandates();
    const targets = (mandates || []).filter(
      (mandate) => mandate.execution_mode === "live" && !mandate.paused
    );
    let paused = 0;
    for (const mandate of targets) {
      try {
        await pauseTradingMandate(mandate.id, "EMERGENCY_PAUSE (web command)");
        paused += 1;
      } catch {
        /* keep pausing the remaining mandates */
      }
    }
    return targets.length === 0 || paused === targets.length;
  } catch {
    return false;
  }
}

/**
 * LIVE trading console plugin.
 *
 * Gating model (server manifest + safety-status, per LIVE_LAUNCH_ARCHITECTURE):
 * 1. The FastAPI manifest (GET /api/frontend/plugins) must include this id —
 *    the Cordis runtime already refuses to load ids absent from the compiled
 *    whitelist, so this is a UX gate only; FastAPI remains the trusted boundary.
 * 2. The plugin then reads `/api/trading/safety-status` and derives ONE state
 *    (UNAVAILABLE / LIVE_DISABLED / PENDING_APPROVAL / KILLED / PAUSED / READY):
 *    - UNAVAILABLE (404/501/network): no panels, only a disabled nav item.
 *    - LIVE_DISABLED: only the overview panel (renders the honest disabled
 *      explanation; the page never fabricates trading UI).
 *    - otherwise: all four panels + the emergency-pause command.
 */
export function apply(ctx: Context) {
  let disposed = false;
  const disposers: Array<() => void> = [];
  ctx.on("dispose", () => {
    disposed = true;
    disposers.splice(0).forEach((unregister) => unregister());
  });

  const registerDisabledNav = () => {
    if (disposed) return;
    disposers.push(
      ctx.navigation.register({
        href: ROUTES.overview,
        label: "LIVE Trading (not enabled)",
        labelKey: "live-trading.nav.disabled",
        disabled: true,
      })
    );
  };

  void (async () => {
    // Gate 1: the server manifest must allow this plugin for this user.
    if (!ctx.entitlements.allowsPlugin(id)) {
      registerDisabledNav();
      return;
    }

    // Gate 2: safety-status must answer. 404/501/network → no panels.
    let safety: TradingSafetyStatus | null = null;
    let unavailable = false;
    try {
      const result = await ctx.api.get<{ safety: TradingSafetyStatus; unavailable?: boolean }>(
        "/api/trading/safety-status",
        { fallback: { safety: null as unknown as TradingSafetyStatus, unavailable: true } }
      );
      unavailable = Boolean(result.unavailable) || !result.safety;
      safety = result.safety ?? null;
    } catch {
      unavailable = true;
    }
    if (disposed) return;

    const state = deriveLiveUiState(safety, unavailable);
    if (state === "UNAVAILABLE") {
      registerDisabledNav();
      return;
    }

    disposers.push(
      ctx.navigation.register({
        href: ROUTES.overview,
        label: "LIVE Trading",
        labelKey: "live-trading.nav.item",
      })
    );

    // The overview panel always registers: it renders the honest disabled
    // panel when the static gate is off.
    disposers.push(
      ctx.panels.register({
        id: "live.overview",
        route: ROUTES.overview,
        title: PANEL_TITLES.overview,
        load: loadConsole("overview"),
      })
    );

    if (state !== "LIVE_DISABLED") {
      for (const view of ["connect", "orders", "account"] as const) {
        disposers.push(
          ctx.panels.register({
            id: `live.${view}`,
            route: ROUTES[view],
            title: PANEL_TITLES[view],
            load: loadConsole(view),
          })
        );
      }
      disposers.push(
        ctx.commands.register({
          id: "live.emergency-pause",
          title: "Pause LIVE trading (emergency)",
          run: async () => {
            await emergencyPauseAllLiveMandates();
          },
        })
      );
    }
  })();
}

export default { id, version, permissions, apply } satisfies FrontendPlugin;
