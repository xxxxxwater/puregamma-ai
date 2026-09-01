"use client";

import { useEffect, useState } from "react";

export type ChronoTier = "full" | "light" | "static";

export const CHRONO_TIER_STORAGE_KEY = "pg:chrono-tier";

const TIER_ORDER: Record<ChronoTier, number> = { full: 2, light: 1, static: 0 };

function clampTier(value: ChronoTier, ceiling: ChronoTier): ChronoTier {
  return TIER_ORDER[value] <= TIER_ORDER[ceiling] ? value : ceiling;
}

function deviceTier(): ChronoTier {
  if (typeof window === "undefined") return "light";
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return "static";
  if (window.matchMedia?.("(prefers-reduced-transparency: reduce)").matches) return "static";
  if (window.matchMedia?.("(max-width: 767px)").matches) return "static";
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8;
  const cores = navigator.hardwareConcurrency ?? 8;
  const lowPower = memory <= 4 || cores <= 4;
  if (window.matchMedia?.("(max-width: 1023px)").matches) return lowPower ? "static" : "light";
  if (lowPower) return "light";
  return "full";
}

export function readStoredChronoTier(ceiling: ChronoTier): ChronoTier | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CHRONO_TIER_STORAGE_KEY);
    if (raw === "full" || raw === "light" || raw === "static") return clampTier(raw, ceiling);
  } catch {
    /* storage unavailable */
  }
  return null;
}

export function storeChronoTier(tier: ChronoTier | null): void {
  if (typeof window === "undefined") return;
  try {
    if (tier === null) window.localStorage.removeItem(CHRONO_TIER_STORAGE_KEY);
    else window.localStorage.setItem(CHRONO_TIER_STORAGE_KEY, tier);
  } catch {
    /* storage unavailable */
  }
}

export { deviceTier as resolveChronoTierDevice };

export function resolveChronoTier(): ChronoTier {
  const device = typeof window === "undefined" ? "light" : deviceTier();
  const stored = readStoredChronoTier(device);
  return clampTier(stored ?? device, device);
}

export function useChronoTierReactive(): ChronoTier {
  const [tier, setTier] = useState<ChronoTier>("light");
  useEffect(() => {
    const recompute = () => setTier(resolveChronoTier());
    recompute();
    const queries = [
      window.matchMedia?.("(prefers-reduced-motion: reduce)"),
      window.matchMedia?.("(prefers-reduced-transparency: reduce)"),
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

export function usePageVisible(): boolean {
  const [visible, setVisible] = useState<boolean>(typeof document === "undefined" || document.visibilityState === "visible");
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return visible;
}

export function useClockNow(intervalMs = 1000): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  const visible = usePageVisible();
  useEffect(() => {
    if (!visible) return;
    const tick = () => setNow(new Date());
    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs, visible]);
  return now;
}

export function formatClockTime(date: Date | null, locale: string, withSeconds = true): string {
  if (!date) return "—";
  try {
    return date.toLocaleTimeString(locale, {
      hour: "2-digit",
      minute: "2-digit",
      ...(withSeconds ? { second: "2-digit" } : {}),
    });
  } catch {
    return "—";
  }
}

export function formatUtcTime(date: Date | null, withSeconds = true): string {
  if (!date) return "—";
  const iso = date.toISOString();
  return withSeconds ? iso.slice(11, 19) : iso.slice(11, 16);
}

/** Reactively track a data attribute on <html> so components re-run when the
 *  theme / visual-style / surface-tier switches without a reload. */
export function useHtmlDataset(name: string): string | undefined {
  const [value, setValue] = useState<string | undefined>(undefined);
  useEffect(() => {
    const el = document.documentElement;
    const read = () => setValue(el.getAttribute("data-" + name) ?? undefined);
    read();
    const observer = new MutationObserver(read);
    observer.observe(el, { attributes: true, attributeFilter: ["data-" + name] });
    window.addEventListener("storage", read);
    return () => {
      observer.disconnect();
      window.removeEventListener("storage", read);
    };
  }, [name]);
  return value;
}

/** Honest market-data status vocabulary (shared by presence/status chips). */
export type MarketStatus = "live" | "delayed" | "stale" | "reconnecting" | "waiting";

export const MARKET_STATUS_WORD: Record<MarketStatus, { en: string; zh: string }> = {
  live: { en: "LIVE", zh: "实时" },
  delayed: { en: "DELAYED", zh: "延迟" },
  stale: { en: "STALE", zh: "过期" },
  reconnecting: { en: "RECONNECTING", zh: "重连中" },
  waiting: { en: "WAITING", zh: "等待数据" },
};
