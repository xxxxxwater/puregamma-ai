"use client";

import { Context } from "cordis";
import { useEffect, type ReactNode } from "react";
import { builtinPluginLoaders } from "@/plugins/builtin/registry";
import type { FrontendPlugin } from "@/plugins/core/contracts";
import { createCoreServices } from "@/plugins/core/services";
import { fetchFrontendPlugins } from "@/plugins/core/services/manifest";

/**
 * The Cordis frontend extension runtime. Client-only by design: the root
 * layout stays a server component and the browser-only Context is created
 * inside an effect, so SSR never touches window/Cordis state.
 *
 * Loading policy:
 * 1. FastAPI manifest (GET /api/frontend/plugins) decides which ids are
 *    enabled for this user/tenant/feature-flag set.
 * 2. Only ids present in the COMPILED builtin whitelist can load — a
 *    server-provided URL is never executed.
 * 3. Plugins register panels/commands/services; unmounting the runtime
 *    stops the context, which disposes every plugin listener, timer and
 *    realtime connection registered through the services.
 */
export function PluginRuntime({ children }: { children: ReactNode }) {
  useEffect(() => {
    let stopped = false;
    const ctx = new Context();
    const services = createCoreServices();

    ctx.set("api", services.api);
    ctx.set("session", services.session);
    ctx.set("entitlements", services.entitlements);
    ctx.set("navigation", services.navigation);
    ctx.set("panels", services.panels);
    ctx.set("commands", services.commands);
    ctx.set("telemetry", services.telemetry);
    ctx.set("realtime", services.realtime);

    // Only ids actually resolved through the compiled whitelist land here.
    const loadedPluginIds: string[] = [];
    void (async () => {
      let manifest;
      try {
        manifest = await fetchFrontendPlugins();
      } catch (error) {
        services.telemetry.track("plugin_manifest_fetch_failed");
        console.error("[plugins] manifest fetch failed", error);
        return;
      }
      if (stopped) return;
      services.entitlements.hydrate(manifest);

      for (const entry of manifest.plugins) {
        if (!entry.enabled || entry.entry !== "builtin") continue;
        const load = builtinPluginLoaders[entry.id as keyof typeof builtinPluginLoaders];
        if (!load) {
          services.telemetry.track("plugin_manifest_unknown_id", { plugin: entry.id });
          continue;
        }
        try {
          const module = (await load()) as FrontendPlugin;
          ctx.plugin({ name: module.id, apply: module.apply });
          loadedPluginIds.push(module.id);
        } catch (error) {
          services.telemetry.track("plugin_load_failed", { plugin: entry.id });
          console.error(`[plugins] failed to load builtin plugin ${entry.id}`, error);
        }
      }

      try {
        await ctx.start();
      } catch (error) {
        console.error("[plugins] runtime failed to start", error);
      }
    })();

    // Development diagnostics seam (never shipped to production bundles):
    // lets the Playwright smoke test observe manifest loading, panel/command
    // registration and realtime teardown from the browser.
    const diagnostics =
      process.env.NODE_ENV === "development"
        ? {
            loadedPlugins: [] as string[],
            panelIds: [] as string[],
            commandIds: [] as string[],
            get realtimeConnections() {
              return services.realtime.connectionCount();
            },
            disposed: false,
          }
        : null;
    if (diagnostics) {
      (window as unknown as { __PUREGAMMA_PLUGIN_RUNTIME__?: unknown }).__PUREGAMMA_PLUGIN_RUNTIME__ = diagnostics;
      const refresh = () => {
        diagnostics.loadedPlugins = [...loadedPluginIds];
        diagnostics.panelIds = services.panels.all().map((panel) => panel.id);
        diagnostics.commandIds = services.commands.list().map((command) => command.id);
      };
      refresh();
      const refreshTimer = window.setInterval(refresh, 250);
      // eslint-disable-next-line no-console
      console.debug("[plugins] development diagnostics exposed");
      return () => {
        stopped = true;
        if (diagnostics) diagnostics.disposed = true;
        window.clearInterval(refreshTimer);
        services.realtime.closeAll();
        ctx.stop();
      };
    }

    return () => {
      stopped = true;
      services.realtime.closeAll();
      ctx.stop();
    };
  }, []);

  return <div className="contents" data-plugin-runtime="active">{children}</div>;
}
