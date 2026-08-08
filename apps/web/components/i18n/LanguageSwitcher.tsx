"use client";

import clsx from "clsx";
import { usePathname, useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { localeCookieName, switchLocalePath, type Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";
import { useLocale } from "./LocaleProvider";

const targets: { locale: Locale; labelKey: "common.language.english" | "common.language.chinese"; ariaKey: "common.language.switchToEnglish" | "common.language.switchToChinese" }[] = [
  { locale: "en", labelKey: "common.language.english", ariaKey: "common.language.switchToEnglish" },
  { locale: "zh", labelKey: "common.language.chinese", ariaKey: "common.language.switchToChinese" }
];

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  function switchTo(nextLocale: Locale) {
    document.cookie = `${localeCookieName}=${nextLocale}; Path=/; Max-Age=31536000; SameSite=Lax`;
    void fetch(`${API_URL}/auth/preferences/locale`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-PG-Locale": nextLocale },
      // Cross-subdomain call: without credentials the session cookie is never
      // sent and the account-level locale preference silently failed with 401.
      credentials: "include",
      body: JSON.stringify({ locale: nextLocale })
    }).catch(() => undefined);
    const search = typeof window !== "undefined" ? window.location.search : "";
    router.push(switchLocalePath(pathname, nextLocale, search));
    router.refresh();
  }

  return (
    <div className={clsx("inline-flex items-center border border-border-pg bg-bg-panel-muted rounded-lg", compact ? "text-xs" : "text-sm")} aria-label={t(locale, "common.language.label")}>
      {targets.map((target) => {
        const active = target.locale === locale;
        return (
          <button
            key={target.locale}
            type="button"
            aria-label={t(locale, target.ariaKey)}
            aria-pressed={active}
            className={clsx("min-h-9 px-2.5 py-1.5 font-medium transition", active ? "bg-pg-white text-pg-black" : "text-text-pg-muted hover:bg-bg-panel hover:text-text-pg")}
            onClick={() => switchTo(target.locale)}
          >
            {t(locale, target.labelKey)}
          </button>
        );
      })}
    </div>
  );
}
