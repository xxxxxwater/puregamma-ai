import type { FrontendPluginManifest, FrontendPluginManifestEntry } from "../contracts";

/**
 * ctx.entitlements — plugin-level permissions derived from the manifest
 * returned by FastAPI (GET /api/frontend/plugins). UX-only: a plugin that
 * claims a permission here still cannot access data the API refuses.
 */
export class EntitlementsService {
  private entries: FrontendPluginManifestEntry[] = [];
  private permissions = new Set<string>();
  private hydrated = false;

  hydrate(manifest: FrontendPluginManifest): void {
    this.entries = manifest.plugins.filter((entry) => entry.enabled);
    this.permissions = new Set(this.entries.flatMap((entry) => entry.permissions));
    this.hydrated = true;
  }

  get isHydrated(): boolean {
    return this.hydrated;
  }

  get availablePlugins(): FrontendPluginManifestEntry[] {
    return [...this.entries];
  }

  allowsPlugin(id: string): boolean {
    return this.entries.some((entry) => entry.id === id);
  }

  can(permission: string): boolean {
    return this.permissions.has(permission);
  }
}
