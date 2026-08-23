import type { ComponentType } from "react";
import type { Context } from "cordis";
import type { ApiClientService } from "./services/api-client";
import type { SessionService } from "./services/session";
import type { EntitlementsService } from "./services/entitlements";
import type { NavigationService } from "./services/navigation";
import type { PanelsService } from "./services/panels";
import type { CommandsService } from "./services/commands";
import type { TelemetryService } from "./services/telemetry";
import type { RealtimeService } from "./services/realtime";

/**
 * PureGamma frontend extension contracts.
 *
 * Cordis is the frontend extension runtime ONLY: React keeps rendering,
 * Next.js keeps routing, and FastAPI remains the only trusted boundary.
 * Permissions here are UX declarations; data access, billing and trading
 * rights are enforced exclusively by the API.
 */

export type FrontendPermission = "read:portfolio" | "read:research" | "trade:paper";

export interface FrontendPluginManifestEntry {
  id: string;
  version: string;
  enabled: boolean;
  entry: "builtin" | string;
  required_entitlements: string[];
  permissions: string[];
  routes: string[];
}

export interface FrontendPluginManifest {
  plugins: FrontendPluginManifestEntry[];
  unavailable?: boolean;
}

export interface PanelDefinition {
  id: string;
  route: string;
  title: string;
  load: () => Promise<{ default: ComponentType<{ locale?: string }> }>;
}

export interface CommandDefinition {
  id: string;
  title: string;
  run: () => void | Promise<void>;
}

export interface PluginNavItem {
  href: string;
  label: string;
}

export interface FrontendPlugin {
  id: string;
  version: string;
  permissions: readonly FrontendPermission[];
  apply(ctx: Context): void | Promise<void>;
}

declare module "cordis" {
  interface Context {
    api: ApiClientService;
    session: SessionService;
    entitlements: EntitlementsService;
    navigation: NavigationService;
    panels: PanelsService;
    commands: CommandsService;
    telemetry: TelemetryService;
    realtime: RealtimeService;
  }
}
