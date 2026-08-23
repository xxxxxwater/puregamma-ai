export { PluginRuntime } from "./core/runtime";
export { PluginPanelSlot, panels } from "./core/services/panels";
export { runPluginCommand, commands } from "./core/services/commands";
export { usePluginNavItems, navigation } from "./core/services/navigation";
export type {
  FrontendPlugin,
  FrontendPluginManifest,
  FrontendPluginManifestEntry,
  FrontendPermission,
  PanelDefinition,
  CommandDefinition,
} from "./core/contracts";
