import { cookies, headers } from "next/headers";
import { defaultLocale, localeCookieName, localeFromAcceptLanguage, normalizeLocale, type Locale } from "./routing";
import { isChinaIP } from "@/lib/geoip";

export function getPreferredLocale(): Locale {
  const cookieLocale = cookies().get(localeCookieName)?.value;
  if (cookieLocale) return normalizeLocale(cookieLocale);
  return localeFromAcceptLanguage(headers().get("accept-language")) || defaultLocale;
}

export async function getPreferredLocaleGeo(): Promise<Locale> {
  const cookieLocale = cookies().get(localeCookieName)?.value;
  if (cookieLocale) return normalizeLocale(cookieLocale);
  const acceptLocale = localeFromAcceptLanguage(headers().get("accept-language"));
  if (acceptLocale !== defaultLocale) return acceptLocale;
  const isCN = await isChinaIP(headers());
  return isCN ? "zh" : defaultLocale;
}
