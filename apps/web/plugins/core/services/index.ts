import { ApiClientService } from "./api-client";
import { SessionService } from "./session";
import { EntitlementsService } from "./entitlements";
import { navigation, NavigationService } from "./navigation";
import { panels, PanelsService } from "./panels";
import { commands, CommandsService } from "./commands";
import { TelemetryService } from "./telemetry";
import { RealtimeService } from "./realtime";

export interface CoreServices {
  api: ApiClientService;
  session: SessionService;
  entitlements: EntitlementsService;
  navigation: NavigationService;
  panels: PanelsService;
  commands: CommandsService;
  telemetry: TelemetryService;
  realtime: RealtimeService;
}

// Module-level singletons: hooks (usePluginNavItems, PluginPanelSlot) read
// the same instances the runtime registers on the Cordis context.
const coreServices: CoreServices = {
  api: new ApiClientService(),
  session: new SessionService(),
  entitlements: new EntitlementsService(),
  navigation,
  panels,
  commands,
  telemetry: new TelemetryService(),
  realtime: new RealtimeService(),
};

export function createCoreServices(): CoreServices {
  return coreServices;
}
