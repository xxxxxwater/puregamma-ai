import type { Context } from "cordis";
import { isLocale } from "@/i18n/routing";
import type { FrontendPlugin } from "@/plugins/core/contracts";

export const id = "puregamma.secretary";
export const version = "1.0.0";
export const permissions = ["read:research"] as const;

/**
 * Registers panels and commands. Panels point at the existing console
 * components through locale-aware adapters; React keeps rendering and the
 * page keeps owning its own data flow until it opts into PluginPanelSlot.
 */
export function apply(ctx: Context) {
  ctx.panels.register({
    id: "secretary.console",
    route: "/secretary",
    title: "Private Secretary",
    load: () =>
      import("@/components/secretary-console").then((module) => ({
        default: ({ locale = "en" }: { locale?: string }) => (
          <module.SecretaryConsole locale={isLocale(locale) ? locale : "en"} />
        ),
      })),
  });

  ctx.panels.register({
    id: "secretary.agent-chat",
    route: "/chat",
    title: "Agent Chat",
    load: () =>
      import("@/components/agent-chat").then((module) => ({
        default: ({ locale = "en" }: { locale?: string }) => (
          <module.AgentChat locale={isLocale(locale) ? locale : "en"} />
        ),
      })),
  });

  ctx.commands.register({
    id: "secretary.refresh",
    title: "Refresh secretary",
    run: async () => {
      await ctx.api.get("/api/secretary", { fallback: {} });
    },
  });

}

export default { id, version, permissions, apply } satisfies FrontendPlugin;
