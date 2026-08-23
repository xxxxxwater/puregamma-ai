import type { Context } from "cordis";
import { isLocale } from "@/i18n/routing";
import type { FrontendPlugin } from "@/plugins/core/contracts";

export const id = "puregamma.trading";
export const version = "1.0.0";
export const permissions = ["trade:paper"] as const;

/**
 * Registers panels and commands. Panels point at the existing console
 * components through locale-aware adapters; React keeps rendering and the
 * page keeps owning its own data flow until it opts into PluginPanelSlot.
 */
export function apply(ctx: Context) {
  // Paper trading is the ONLY surface this plugin registers. Live trading
  // stays behind the FastAPI gates; trade:paper is display + intent
  // submission only.
  const views = ["paper", "positions", "risk", "runtime"] as const;
  for (const view of views) {
    ctx.panels.register({
      id: `trading.${view}`,
      route: `/trading/${view}`,
      title: `Trading — ${view}`,
      load: () =>
        import("@/components/strategy-runtime-console").then((module) => ({
          default: ({ locale = "en" }: { locale?: string }) => (
            <module.StrategyRuntimeConsole locale={isLocale(locale) ? locale : "en"} view={view} />
          ),
        })),
    });
  }

}

export default { id, version, permissions, apply } satisfies FrontendPlugin;
