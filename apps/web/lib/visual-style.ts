export const VISUAL_STYLE_KEY = "pg_visual_style";

export type VisualStyle = "glass" | "classic";

/**
 * Build-time default. Glass ships as the default; set
 * NEXT_PUBLIC_VISUAL_STYLE_DEFAULT=classic to roll the default back without a
 * code change (users who saved a preference keep their own choice).
 */
export const DEFAULT_VISUAL_STYLE: VisualStyle =
  process.env.NEXT_PUBLIC_VISUAL_STYLE_DEFAULT === "classic" ? "classic" : "glass";

export type SurfaceTier = "financial" | "ocean";

/** Read the persisted visual style; glass is the default. */
export function readVisualStyle(): VisualStyle {
  if (typeof window === "undefined") return DEFAULT_VISUAL_STYLE;
  try {
    return window.localStorage.getItem(VISUAL_STYLE_KEY) === "classic" ? "classic" : DEFAULT_VISUAL_STYLE;
  } catch {
    return DEFAULT_VISUAL_STYLE;
  }
}

/** Apply the visual style to <html data-visual-style> and persist it. */
export function applyVisualStyle(style: VisualStyle): void {
  document.documentElement.dataset.visualStyle = style;
  try {
    window.localStorage.setItem(VISUAL_STYLE_KEY, style);
  } catch {
    /* A blocked storage backend must not prevent the live style switch. */
  }
}

const FINANCIAL_PREFIXES = [
  "/portfolio",
  "/trading",
  "/billing",
  "/admin",
  "/gateway",
  "/account",
  "/daily-push",
  "/backtest",
  "/integrations",
  "/data-sources",
  "/signals",
  "/playbooks",
  "/memory",
  "/strategies",
  "/nautilus",
];

const OCEAN_PREFIXES = ["/dashboard", "/chat", "/research", "/secretary"];

/**
 * Route-derived surface tier. Financial/security pages get higher-opacity
 * glass so prices, positions, alerts and action buttons stay crisp; Ocean
 * pages disable the extra blur to avoid double-blur over the Ocean layers.
 * Returns null for the standard tier.
 */
export function surfaceTierForPath(pathname: string): SurfaceTier | null {
  const stripped = pathname.replace(/^\/(en|zh)(?=\/|$)/, "");
  if (OCEAN_PREFIXES.some((prefix) => stripped === prefix || stripped.startsWith(`${prefix}/`))) {
    return "ocean";
  }
  if (FINANCIAL_PREFIXES.some((prefix) => stripped === prefix || stripped.startsWith(`${prefix}/`))) {
    return "financial";
  }
  return null;
}

/** Apply (or clear) the surface tier on <html data-surface-tier>. */
export function applySurfaceTier(tier: SurfaceTier | null): void {
  if (tier) {
    document.documentElement.dataset.surfaceTier = tier;
  } else {
    delete document.documentElement.dataset.surfaceTier;
  }
}
