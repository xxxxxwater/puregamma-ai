import { cookies, headers } from "next/headers";
import { defaultLocale, localeCookieName, localeFromAcceptLanguage, normalizeLocale, type Locale } from "./routing";

export function getPreferredLocale(): Locale {
  const cookieLocale = cookies().get(localeCookieName)?.value;
  if (cookieLocale) return normalizeLocale(cookieLocale);
  return localeFromAcceptLanguage(headers().get("accept-language")) || defaultLocale;
}
