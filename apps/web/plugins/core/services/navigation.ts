"use client";

import { useEffect, useState } from "react";
import type { PluginNavItem } from "../contracts";

/**
 * ctx.navigation — nav items registered by plugins. The static sidebar
 * (components/nav.tsx) stays the owner of core navigation; plugins only
 * append to this registry, which can be rendered by any consumer via
 * usePluginNavItems().
 */
export class NavigationService {
  private items: PluginNavItem[] = [];
  private listeners = new Set<() => void>();

  register(item: PluginNavItem): () => void {
    this.items = [...this.items, item];
    this.emit();
    return () => {
      this.items = this.items.filter((existing) => existing !== item);
      this.emit();
    };
  }

  get all(): PluginNavItem[] {
    return [...this.items];
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }
}

export const navigation = new NavigationService();

export function usePluginNavItems(): PluginNavItem[] {
  const [items, setItems] = useState<PluginNavItem[]>(() => navigation.all);
  useEffect(() => navigation.subscribe(() => setItems(navigation.all)), []);
  return items;
}
