import type { Context } from "cordis";
import { isLocale } from "@/i18n/routing";
import type { FrontendPlugin } from "@/plugins/core/contracts";

export const id = "puregamma.research";
export const version = "1.0.0";
export const permissions = ["read:research"] as const;

/**
 * Registers panels and commands. Panels point at the existing console
 * components through locale-aware adapters; React keeps rendering and the
 * page keeps owning its own data flow until it opts into PluginPanelSlot.
 */
export function apply(ctx: Context) {
  ctx.panels.register({
    id: "research.console",
    route: "/research",
    title: "Research",
    load: () =>
      import("@/components/research-console").then((module) => ({
        default: ({ locale = "en" }: { locale?: string }) => (
          <module.ResearchConsole locale={isLocale(locale) ? locale : "en"} />
        ),
      })),
  });

  // /reports is intentionally not panel-registered yet: ReportsConsole
  // requires server-fetched data props, so the reports page keeps owning its
  // data flow until it adopts PluginPanelSlot with a data-aware adapter.
  ctx.panels.register({
    id: "research.backtest",
    route: "/backtest",
    title: "Backtest Lab",
    load: () =>
      import("@/components/backtest-lab").then((module) => ({
        default: ({ locale = "en" }: { locale?: string }) => (
          <module.BacktestLab locale={isLocale(locale) ? locale : "en"} />
        ),
      })),
  });

  ctx.commands.register({
    id: "research.refresh",
    title: "Refresh research",
    run: async () => {
      await ctx.api.market.snapshot();
    },
  });

}

export default { id, version, permissions, apply } satisfies FrontendPlugin;
