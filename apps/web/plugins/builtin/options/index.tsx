import type { Context } from "cordis";
import { isLocale } from "@/i18n/routing";
import type { FrontendPlugin } from "@/plugins/core/contracts";

export const id = "puregamma.options";
export const version = "1.0.0";
export const permissions = ["read:research"] as const;

/**
 * Registers panels and commands. Panels point at the existing console
 * components through locale-aware adapters; React keeps rendering and the
 * page keeps owning its own data flow until it opts into PluginPanelSlot.
 */
export function apply(ctx: Context) {
  ctx.panels.register({
    id: "options.surface",
    route: "/options",
    title: "Options Intelligence",
    load: () =>
      import("@/components/options-surface").then((module) => ({
        default: ({ locale = "en" }: { locale?: string }) => (
          <module.OptionsSurface locale={isLocale(locale) ? locale : "en"} />
        ),
      })),
  });

}

export default { id, version, permissions, apply } satisfies FrontendPlugin;
