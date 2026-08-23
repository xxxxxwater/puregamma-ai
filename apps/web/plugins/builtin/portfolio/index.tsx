import type { Context } from "cordis";
import { isLocale } from "@/i18n/routing";
import type { FrontendPlugin } from "@/plugins/core/contracts";

export const id = "puregamma.portfolio";
export const version = "1.0.0";
export const permissions = ["read:portfolio"] as const;

/**
 * Registers panels and commands. Panels point at the existing console
 * components through locale-aware adapters; React keeps rendering and the
 * page keeps owning its own data flow until it opts into PluginPanelSlot.
 */
export function apply(ctx: Context) {
  ctx.panels.register({
    id: "portfolio.overview",
    route: "/portfolio",
    title: "Portfolio",
    load: () =>
      import("@/components/portfolio-console").then((module) => ({
        default: ({ locale = "en" }: { locale?: string }) => (
          <module.PortfolioConsole locale={isLocale(locale) ? locale : "en"} />
        ),
      })),
  });

  ctx.commands.register({
    id: "portfolio.refresh",
    title: "Refresh portfolio",
    run: async () => {
      await ctx.api.portfolio.snapshot();
    },
  });

}

export default { id, version, permissions, apply } satisfies FrontendPlugin;
