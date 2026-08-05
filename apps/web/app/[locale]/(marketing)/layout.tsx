import type { ReactNode } from "react";
import Link from "next/link";
import Image from "next/image";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { AppearanceControls } from "@/components/appearance-controls";
import { DisclaimerFooter } from "@/components/puregamma";
import { withLocale, type Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export default function MarketingLayout({ children, params }: { children: ReactNode; params: { locale: Locale } }) {
  const locale = params.locale;
  const zh = locale === "zh";
  return (
    <div className="min-h-screen bg-bg-app">
      <header className="sticky top-0 z-20 border-b border-border-pg bg-bg-app/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-4 py-3 md:px-6">
          <Link href={withLocale(locale, "/")} className="flex min-w-0 items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={24} height={24} />PureGamma AI
          </Link>
          <nav className="flex shrink-0 items-center gap-2 text-xs">
            <LanguageSwitcher compact />
            <AppearanceControls locale={locale} showFontScale={false} />
            <Link href={withLocale(locale, "/signup")} className="border border-border-pg-strong bg-pg-white px-3 py-1.5 font-semibold text-pg-black hover:bg-pg-white-soft">{t(locale, "common.nav.signup")}</Link>
            <Link href={withLocale(locale, "/login")} className="border border-border-pg px-3 py-1.5 text-text-pg hover:border-border-pg-strong">{t(locale, "common.nav.signin")}</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-4 py-6 md:px-6">{children}</main>
      <div className="mx-auto max-w-[1200px] px-4 pb-8 md:px-6">
        <DisclaimerFooter locale={locale} />
      </div>
      <p className="sr-only">{zh ? "PureGamma AI 研究平台" : "PureGamma AI research platform"}</p>
    </div>
  );
}
