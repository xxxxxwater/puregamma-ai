"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import type { PanelDefinition } from "../contracts";

/**
 * ctx.panels — route-keyed panel registry. Plugins register a panel per
 * route; pages opt in by rendering <PluginPanelSlot route="/portfolio" />
 * with their existing markup as fallback. React renders, Cordis only
 * manages which panel is registered and its lifecycle.
 */
export class PanelsService {
  private panels = new Map<string, PanelDefinition>();

  register(definition: PanelDefinition): () => void {
    this.panels.set(definition.route, definition);
    return () => {
      if (this.panels.get(definition.route) === definition) {
        this.panels.delete(definition.route);
      }
    };
  }

  get(route: string): PanelDefinition | undefined {
    return this.panels.get(route);
  }

  all(): PanelDefinition[] {
    return [...this.panels.values()];
  }
}

export const panels = new PanelsService();

/** Lazy-renders the plugin panel registered for `route`, if any. */
export function PluginPanelSlot({ route, fallback = null }: { route: string; fallback?: ReactNode }) {
  const [definition] = useState<PanelDefinition | undefined>(() => panels.get(route));
  const [Component, setComponent] = useState<ComponentType<{ locale?: string }> | null>(null);
  useEffect(() => {
    let active = true;
    if (!definition) return;
    definition
      .load()
      .then((module) => {
        if (active) setComponent(() => module.default);
      })
      .catch(() => {
        /* a failed panel load must never break the page */
      });
    return () => {
      active = false;
    };
  }, [definition]);
  if (!Component) return <>{fallback}</>;
  return <Component />;
}
