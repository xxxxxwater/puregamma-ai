export const locales = ["en", "zh"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";
export const localeCookieName = "pg_locale";

export const localePrefixPattern = /^\/(en|zh)(?=\/|$)/;

export const legacyLocaleRoutes = [
  "/dashboard",
  "/news",
  "/reports",
  "/options",
  "/signals",
  "/playbooks",
  "/portfolio",
  "/integrations",
  "/data-sources",
  "/nautilus",
  "/strategies",
  "/trading/paper",
  "/trading/runtime",
  "/trading/positions",
  "/trading/risk",
  "/daily-push",
  "/billing",
  "/admin",
  "/internal/login",
  "/login",
  "/signup",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/onboarding/assets",
  "/onboarding/style",
  "/onboarding/channels"
] as const;

export function isLocale(value: string | undefined | null): value is Locale {
  return value === "en" || value === "zh";
}

export function normalizeLocale(value: string | undefined | null): Locale {
  return isLocale(value) ? value : defaultLocale;
}

export function localeFromAcceptLanguage(value: string | null): Locale {
  if (!value) return defaultLocale;
  const parts = value
    .split(",")
    .map((item) => item.trim().split(";")[0]?.toLowerCase())
    .filter(Boolean);
  return parts.some((part) => part === "zh" || part.startsWith("zh-")) ? "zh" : defaultLocale;
}

export function stripLocale(pathname: string): string {
  const stripped = pathname.replace(localePrefixPattern, "");
  return stripped || "/";
}

export function pathLocale(pathname: string): Locale | undefined {
  const match = pathname.match(localePrefixPattern);
  return isLocale(match?.[1]) ? match[1] : undefined;
}

export function withLocale(locale: Locale, href: string): string {
  if (/^https?:\/\//.test(href) || href.startsWith("#")) return href;
  const [path = "/", query = ""] = href.split("?");
  const normalizedPath = stripLocale(path.startsWith("/") ? path : `/${path}`);
  const suffix = normalizedPath === "/" ? "" : normalizedPath;
  return `/${locale}${suffix}${query ? `?${query}` : ""}`;
}

export function switchLocalePath(pathname: string, locale: Locale, search = ""): string {
  const unprefixed = stripLocale(pathname);
  const path = withLocale(locale, unprefixed);
  return `${path}${search}`;
}
