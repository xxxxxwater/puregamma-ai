"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Shared appearance state.
 *
 * `AppearanceControls` is mounted three times (sidebar rail, desktop top bar,
 * mobile top bar). Each instance used to hold its own `useState`, so switching
 * the theme in the top bar left the sidebar's icon showing the old theme until
 * a reload, and there was no cross-tab sync at all.
 *
 * This is a module-level store read through `useSyncExternalStore`, so every
 * mount — and every tab, via the `storage` event — observes one value.
 *
 * The stored values are deliberately the same ones the pre-paint script in
 * `app/layout.tsx` reads, so nothing here fights the first paint.
 */

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";
export type FontScale = "compact" | "default" | "large";

export const THEME_KEY = "pg_theme";
export const FONT_SCALE_KEY = "pg_font_scale";
export const SCALES: FontScale[] = ["compact", "default", "large"];

type State = { preference: ThemePreference; resolved: ResolvedTheme; fontScale: FontScale };

const listeners = new Set<() => void>();
let state: State = { preference: "system", resolved: "light", fontScale: "default" };
let initialized = false;

function darkQuery(): MediaQueryList | null {
  return typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
}

function systemTheme(): ResolvedTheme {
  return darkQuery()?.matches ? "dark" : "light";
}

function readPreference(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_KEY);
    // Absent means "System", which is also the pre-paint script's default.
    // These two MUST agree, or the first frame shows one theme and hydration
    // immediately switches to another.
    return raw === "light" || raw === "dark" ? raw : "system";
  } catch {
    // Private mode / disabled storage must still render a usable theme.
    return "system";
  }
}

function readFontScale(): FontScale {
  try {
    const raw = window.localStorage.getItem(FONT_SCALE_KEY);
    return raw === "compact" || raw === "large" ? raw : "default";
  } catch {
    return "default";
  }
}

/** Write the resolved theme to the document. Always light|dark, never absent. */
function paint(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
}

function emit() {
  for (const listener of listeners) listener();
}

function setState(next: State) {
  state = next;
  emit();
}

/** Re-read storage + OS preference and repaint. Idempotent. */
function sync() {
  const preference = readPreference();
  // Nothing stored means LIGHT, not the OS preference: the light identity is
  // the product default and only an explicit "system" choice follows the OS.
  const resolved = preference === "system" ? systemTheme() : preference;
  const fontScale = readFontScale();
  document.documentElement.dataset.fontScale = fontScale;
  paint(resolved);
  setState({ preference, resolved, fontScale });
}

function ensureInitialized() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;

  const preference = readPreference();
  const fontScale = readFontScale();
  // `resolved` is whatever the pre-paint script already painted for the
  // non-system cases; only "system" needs the live OS query.
  state = { preference, resolved: preference === "system" ? systemTheme() : preference, fontScale };

  darkQuery()?.addEventListener("change", () => {
    // Only meaningful while following the system.
    if (state.preference === "system") sync();
  });

  // Another tab changed the preference.
  window.addEventListener("storage", (event) => {
    if (event.key === null || event.key === THEME_KEY || event.key === FONT_SCALE_KEY) sync();
  });
}

function subscribe(listener: () => void): () => void {
  ensureInitialized();
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function getSnapshot(): State {
  return state;
}

// `useSyncExternalStore` compares snapshots by identity, so the server snapshot
// must be a STABLE reference. Returning a fresh object here made React warn
// that the result "should be cached to avoid an infinite loop" and would have
// re-rendered every appearance control on every pass.
const SERVER_STATE: State = { preference: "system", resolved: "light", fontScale: "default" };

function getServerSnapshot(): State {
  return SERVER_STATE;
}

export function useAppearance() {
  const current = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setPreference = useCallback((next: ThemePreference) => {
    try {
      if (next === "system") window.localStorage.removeItem(THEME_KEY);
      else window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // Storage unavailable: still apply for this session.
    }
    const resolved = next === "system" ? systemTheme() : next;
    paint(resolved);
    setState({ ...state, preference: next, resolved });
  }, []);

  const setFontScale = useCallback((next: FontScale) => {
    try {
      window.localStorage.setItem(FONT_SCALE_KEY, next);
    } catch {
      // ignored
    }
    document.documentElement.dataset.fontScale = next;
    setState({ ...state, fontScale: next });
  }, []);

  return { ...current, setPreference, setFontScale };
}

/** Cycle order for the compact control: system → light → dark → system. */
export const THEME_CYCLE: ThemePreference[] = ["system", "light", "dark"];
