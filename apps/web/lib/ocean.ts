"use client";

import { useEffect, useState } from "react";

/**
 * Motion and performance preferences for the Agent/Research visual system.
 *
 * Rules enforced here (single source of truth for every ocean component):
 * - `prefers-reduced-motion` always resolves to the static tier.
 * - Small screens and low-power devices never run the full effect.
 * - The user can force a lower tier from OceanShell's degrade control.
 * - Financial surfaces (Portfolio / NAV / Trading / Trading Safety) must not
 *   use any of these helpers at all.
 */

export type MotionTier = "full" | "light" | "static";

export const OCEAN_TIER_STORAGE_KEY = "pg:ocean-tier";

const TIER_ORDER: Record<MotionTier, number> = { full: 2, light: 1, static: 0 };

function clampTier(value: MotionTier, ceiling: MotionTier): MotionTier {
  return TIER_ORDER[value] <= TIER_ORDER[ceiling] ? value : ceiling;
}

function deviceTier(): MotionTier {
  if (typeof window === "undefined") return "light";
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return "static";
  if (window.matchMedia?.("(max-width: 767px)").matches) return "static"; // phones: static gradient + tap ripple only
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8;
  const cores = navigator.hardwareConcurrency ?? 8;
  const lowPower = memory <= 4 || cores <= 4;
  if (window.matchMedia?.("(max-width: 1023px)").matches) return lowPower ? "static" : "light"; // tablets: reduced intensity
  if (lowPower) return "light";
  return "full";
}

/** User-persisted preference, if any, capped by the device ceiling. */
export function readStoredTier(ceiling: MotionTier): MotionTier | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(OCEAN_TIER_STORAGE_KEY);
    if (raw === "full" || raw === "light" || raw === "static") return clampTier(raw, ceiling);
  } catch {
    /* storage unavailable */
  }
  return null;
}

export function storeTier(tier: MotionTier | null): void {
  if (typeof window === "undefined") return;
  try {
    if (tier === null) window.localStorage.removeItem(OCEAN_TIER_STORAGE_KEY);
    else window.localStorage.setItem(OCEAN_TIER_STORAGE_KEY, tier);
  } catch {
    /* storage unavailable */
  }
}

export { deviceTier as resolveMotionTierDevice };

/** Plain resolver (not a hook): device tier, then user preference, then ceiling. */
export function resolveMotionTier(): MotionTier {
  const device = typeof window === "undefined" ? "light" : deviceTier();
  const stored = readStoredTier(device);
  return clampTier(stored ?? device, device);
}

/** Reactive hook: recomputes the tier when media queries or storage change. */
export function useMotionTierReactive(): MotionTier {
  const [tier, setTier] = useState<MotionTier>("light");
  useEffect(() => {
    const recompute = () => setTier(resolveMotionTier());
    recompute();
    const queries = [
      window.matchMedia?.("(prefers-reduced-motion: reduce)"),
      window.matchMedia?.("(max-width: 767px)"),
      window.matchMedia?.("(max-width: 1023px)"),
    ].filter(Boolean) as MediaQueryList[];
    queries.forEach((query) => query.addEventListener?.("change", recompute));
    window.addEventListener("storage", recompute);
    window.addEventListener("focus", recompute);
    return () => {
      queries.forEach((query) => query.removeEventListener?.("change", recompute));
      window.removeEventListener("storage", recompute);
      window.removeEventListener("focus", recompute);
    };
  }, []);
  return tier;
}

/** True while the document tab is visible; false when hidden. */
export function usePageVisible(): boolean {
  const [visible, setVisible] = useState<boolean>(typeof document === "undefined" || document.visibilityState === "visible");
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return visible;
}

/**
 * Whether an SSE connection failure should silently fall back to polling.
 * Never used to mark a server-side run as failed.
 */
export const OCEAN_POLL_INTERVAL_ACTIVE_MS = 10_000;
export const OCEAN_POLL_INTERVAL_IDLE_MS = 30_000;
