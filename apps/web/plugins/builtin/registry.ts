import type { FrontendPlugin } from "@/plugins/core/contracts";

/**
 * Compiled whitelist: the ONLY mapping from plugin ids to code. The
 * manifest from FastAPI may enable a plugin id, but unless that id exists
 * in this bundle it cannot run. Third-party / marketplace plugins would
 * require signature checks, pinned versions, review and an isolated
 * iframe/origin — never this map.
 */
export const builtinPluginLoaders = {
  // Dynamic import resolves an ES module namespace. Extract its default
  // export so the runtime always receives a FrontendPlugin, not its wrapper.
  "puregamma.portfolio": () => import("./portfolio").then(({ default: plugin }) => plugin),
  "puregamma.research": () => import("./research").then(({ default: plugin }) => plugin),
  "puregamma.options": () => import("./options").then(({ default: plugin }) => plugin),
  "puregamma.secretary": () => import("./secretary").then(({ default: plugin }) => plugin),
  "puregamma.trading": () => import("./trading").then(({ default: plugin }) => plugin),
} as const;

export type BuiltinPluginId = keyof typeof builtinPluginLoaders;
