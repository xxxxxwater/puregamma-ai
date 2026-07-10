import { defaultLocale, type Locale } from "@/i18n/routing";

function intlLocale(locale: Locale) {
  return locale === "zh" ? "zh-CN" : "en-US";
}

function resolveLocaleAndValue(first: Locale | number, second?: number | boolean): { locale: Locale; value: number; compact: boolean } {
  if (typeof first === "number") {
    return { locale: defaultLocale, value: first, compact: typeof second === "boolean" ? second : false };
  }
  return { locale: first, value: typeof second === "number" ? second : 0, compact: false };
}

export function formatCurrency(value: number, compact?: boolean): string;
export function formatCurrency(locale: Locale, value: number, compact?: boolean): string;
export function formatCurrency(first: Locale | number, second?: number | boolean, third = false) {
  const resolved = resolveLocaleAndValue(first, second);
  const compact = typeof first === "string" ? third : resolved.compact;
  return new Intl.NumberFormat(intlLocale(resolved.locale), {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: compact ? 1 : 2,
    notation: compact ? "compact" : "standard"
  }).format(resolved.value);
}

export function formatPercent(value: number): string;
export function formatPercent(locale: Locale, value: number): string;
export function formatPercent(first: Locale | number, second?: number) {
  const value = typeof first === "number" ? first : second || 0;
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function formatNumber(value: number): string;
export function formatNumber(locale: Locale, value: number): string;
export function formatNumber(first: Locale | number, second?: number) {
  const locale = typeof first === "string" ? first : defaultLocale;
  const value = typeof first === "number" ? first : second || 0;
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 2 }).format(value);
}

export function formatCompactNumber(value: number): string;
export function formatCompactNumber(locale: Locale, value: number): string;
export function formatCompactNumber(first: Locale | number, second?: number) {
  const locale = typeof first === "string" ? first : defaultLocale;
  const value = typeof first === "number" ? first : second || 0;
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 2, notation: "compact" }).format(value);
}

export function formatDate(value: string | Date): string;
export function formatDate(locale: Locale, value: string | Date): string;
export function formatDate(first: Locale | string | Date, second?: string | Date) {
  const locale = typeof first === "string" && (first === "en" || first === "zh") ? first : defaultLocale;
  const value = locale === first ? second : first;
  return new Intl.DateTimeFormat(intlLocale(locale), { dateStyle: "medium" }).format(new Date(value || Date.now()));
}

export function formatDateTime(value: string | Date): string;
export function formatDateTime(locale: Locale, value: string | Date): string;
export function formatDateTime(first: Locale | string | Date, second?: string | Date) {
  const locale = typeof first === "string" && (first === "en" || first === "zh") ? first : defaultLocale;
  const value = locale === first ? second : first;
  return new Intl.DateTimeFormat(intlLocale(locale), { dateStyle: "medium", timeStyle: "short" }).format(new Date(value || Date.now()));
}

export function formatRelativeTime(locale: Locale, value: Date | string) {
  const date = new Date(value);
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
    ["second", 1]
  ];
  const [unit, seconds] = units.find(([, seconds]) => Math.abs(diffSeconds) >= seconds) || ["second", 1];
  return new Intl.RelativeTimeFormat(intlLocale(locale), { numeric: "auto" }).format(Math.round(diffSeconds / seconds), unit);
}

export function formatCryptoAmount(value: number, symbol: "BTC" | "ETH" | string, locale: Locale = defaultLocale) {
  const decimals = symbol === "BTC" || symbol === "ETH" ? 4 : 2;
  return `${new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: decimals }).format(value)} ${symbol}`;
}
