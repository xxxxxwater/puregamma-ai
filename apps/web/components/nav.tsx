"use client";

import Link from "next/link";
import Image from "next/image";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Bell, BookOpen, Bot, BriefcaseBusiness, Chrome, Code2, CreditCard, FlaskConical, Gauge, HeartHandshake, LayoutDashboard, LifeBuoy, Menu, MessageCircle, Network, UserRound, X, type LucideIcon } from "lucide-react";
import { AppearanceControls } from "@/components/appearance-controls";
import { PlanBadge, Badge } from "@/components/puregamma";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { LocaleProvider } from "@/components/i18n/LocaleProvider";
import type { Locale } from "@/i18n/routing";
import { stripLocale, withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";
import type { TranslationKey } from "@/lib/translations";
import { getMe, AUTH_EXPIRED_EVENT } from "@/lib/api";
import { publishUserState, USER_STATE_EVENT, type SessionUserState } from "@/lib/user-state";

type NavItem = {
  href: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
};

type NavGroup = {
  labelKey: TranslationKey;
  items: NavItem[];
};

type StoredUser = SessionUserState;

const groups: NavGroup[] = [
  {
    labelKey: "common.nav.groups.research",
    items: [
      { href: "/dashboard", labelKey: "common.nav.dashboard", icon: LayoutDashboard },
      { href: "/chat", labelKey: "common.nav.chat", icon: Bot },
      { href: "/reports", labelKey: "common.nav.reports", icon: BookOpen },
      { href: "/options", labelKey: "common.nav.options", icon: Gauge },
      { href: "/backtest", labelKey: "common.nav.backtest", icon: FlaskConical }
    ]
  },
  {
    labelKey: "common.nav.groups.portfolio",
    items: [
      { href: "/portfolio", labelKey: "common.nav.nav", icon: BriefcaseBusiness },
      { href: "/secretary", labelKey: "common.nav.secretary", icon: HeartHandshake },
      { href: "/api", labelKey: "common.nav.apiDocs", icon: Code2 },
      { href: "/docs", labelKey: "common.nav.docs", icon: LifeBuoy }
    ]
  },
  {
    labelKey: "common.nav.groups.company",
    items: [
      { href: "/billing", labelKey: "common.nav.billing", icon: CreditCard },
      { href: "/gateway", labelKey: "common.nav.gateway", icon: Network },
      { href: "/account", labelKey: "common.nav.account", icon: UserRound }
    ]
  }
];

function AuthExpiredRedirector({ locale }: { locale: Locale }) {
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    const handler = () => {
      const returnTo = stripLocale(pathname || "/");
      router.replace(withLocale(locale, `/login?returnTo=${encodeURIComponent(returnTo)}`));
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handler);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
  }, [locale, pathname, router]);
  return null;
}

export function AppShell({ children, locale }: { children: ReactNode; locale: Locale }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const pathname = usePathname();
  // The root <html> element is shared across locales; keep its lang accurate
  // for SEO and assistive technology.
  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname, locale]);
  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNavOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);
  return (
    <LocaleProvider locale={locale}>
      <div className="relative min-h-screen">
        <AuthExpiredRedirector locale={locale} />
        <SidebarNav locale={locale} />
        <MobileNavDrawer locale={locale} open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

        <div className="lg:pl-72">
          <TopStatusBar locale={locale} onMenuClick={() => setMobileNavOpen(true)} />

          <main className="mx-auto max-w-[1440px] px-4 py-5 md:px-6">
            {children}
          </main>
        </div>
      </div>
    </LocaleProvider>
  );
}

export function MobileNavDrawer({ locale, open, onClose }: { locale: Locale; open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const activePathname = stripLocale(pathname);
  return (
    <>
      {open ? <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={onClose} aria-hidden /> : null}
      <div role="dialog" aria-modal="true" aria-label={locale === "zh" ? "主导航" : "Primary navigation"} className={`fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] transform flex-col border-r border-border-pg bg-bg-panel p-4 transition-transform duration-200 lg:hidden ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between gap-2">
          <Link href={withLocale(locale, "/")} className="flex min-w-0 items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={24} height={24} />PureGamma AI
          </Link>
          <button type="button" onClick={onClose} aria-label={locale === "zh" ? "关闭导航" : "Close navigation"} className="grid h-9 w-9 shrink-0 place-items-center border border-border-pg text-text-pg-muted hover:border-border-pg-strong rounded-lg"><X className="h-4 w-4" /></button>
        </div>
        <nav className="mt-6 flex-1 space-y-7 overflow-y-auto" aria-label={locale === "zh" ? "主导航" : "Primary navigation"}>
          {groups.map((group) => (
            <div key={group.labelKey}>
              <div className="mb-2 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-text-pg-dim">{t(locale, group.labelKey)}</div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = item.href === "/" ? activePathname === "/" : activePathname.startsWith(item.href);
                  return (
                    <Link key={item.href} href={withLocale(locale, item.href)} onClick={onClose} aria-current={active ? "page" : undefined} className={`flex items-center gap-2 border px-3 py-2 text-sm  rounded-lg ${active ? "border-border-pg-strong bg-bg-panel-muted text-text-pg" : "border-transparent text-text-pg-muted hover:border-border-pg hover:bg-bg-panel-muted hover:text-text-pg"}`}>
                      <Icon className="h-4 w-4" aria-hidden />
                      {t(locale, item.labelKey)}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <Link href={withLocale(locale, "/account#imessage-bind")} onClick={onClose} className="flex items-center gap-2 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg">
          <MessageCircle className="h-4 w-4" aria-hidden />
          {locale === "zh" ? "绑定 iMessage" : "Bind iMessage"}
        </Link>
      </div>
    </>
  );
}

export function SidebarNav({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const activePathname = stripLocale(pathname);
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 border-r border-border-pg bg-bg-panel p-4 lg:block">
      <Link href={withLocale(locale, "/")} className="flex items-center gap-2 text-lg font-semibold text-text-pg">
        <Image src="/logo.png" alt="PureGamma" width={24} height={24} />PureGamma AI
      </Link>
      <div className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "common.nav.tagline")}</div>
      <div className="mt-4">
        <div className="flex items-center gap-2"><LanguageSwitcher compact /><AppearanceControls locale={locale} /></div>
      </div>
      <nav className="mt-8 space-y-7">
        {groups.map((group) => (
          <div key={group.labelKey}>
            <div className="mb-2 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-text-pg-dim">{t(locale, group.labelKey)}</div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.href === "/" ? activePathname === "/" : activePathname.startsWith(item.href);
                return (
                  <Link key={item.href} href={withLocale(locale, item.href)} className={`flex items-center gap-2 border px-3 py-2 text-sm  rounded-lg ${active ? "border-border-pg-strong bg-bg-panel-muted text-text-pg" : "border-transparent text-text-pg-muted hover:border-border-pg hover:bg-bg-panel-muted hover:text-text-pg"}`}>
                    <Icon className="h-4 w-4" aria-hidden />
                    {t(locale, item.labelKey)}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <Link href={withLocale(locale, "/account#imessage-bind")} className="absolute bottom-5 left-4 right-4 flex items-center gap-2 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg">
        <MessageCircle className="h-4 w-4" aria-hidden />
        {locale === "zh" ? "绑定 iMessage" : "Bind iMessage"}
      </Link>
    </aside>
  );
}

export function TopStatusBar({ locale, onMenuClick }: { locale: Locale; onMenuClick: () => void }) {
  const [storedUser, setStoredUser] = useState<StoredUser | null>(null);
  const refreshUser = useCallback(async () => {
    const result = await getMe();
    setStoredUser(result.user);
    publishUserState(result.user, true);
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = () => refreshUser().catch((error: unknown) => {
      // Only drop the session UI on a definitive 401; transient errors (429, network)
      // must not flip the top bar to "signed out".
      const status = (error as { status?: number } | null)?.status;
      if (active && status === 401) setStoredUser(null);
    });
    const handleUserState = (event: Event) => {
      const detail = (event as CustomEvent<SessionUserState>).detail;
      if (detail && active) setStoredUser((current) => ({ ...(current || {}), ...detail }));
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    void refresh();
    window.addEventListener(USER_STATE_EVENT, handleUserState);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", handleVisibility);
    const refreshTimer = window.setInterval(refresh, 60_000);
    return () => {
      active = false;
      window.clearInterval(refreshTimer);
      window.removeEventListener(USER_STATE_EVENT, handleUserState);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [refreshUser]);
  return (
    <header className="sticky top-0 z-20 border-b border-border-pg bg-bg-app/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-2 px-3 py-2.5 sm:gap-4 sm:px-4 sm:py-3">
        <button type="button" onClick={onMenuClick} aria-label={locale === "zh" ? "打开导航" : "Open navigation"} className="grid h-9 w-9 shrink-0 place-items-center border border-border-pg text-text-pg-muted hover:border-border-pg-strong lg:hidden rounded-lg"><Menu className="h-4 w-4" /></button>
        <Link href={withLocale(locale, "/")} className="min-w-0 shrink flex items-center gap-2 truncate font-semibold text-text-pg lg:hidden">
          <Image src="/logo.png" alt="PureGamma" width={20} height={20} />
          PureGamma AI
        </Link>
        <div className="hidden items-center gap-2 text-xs md:flex">
          <PlanBadge plan={storedUser?.plan || "Free"} tier={storedUser?.membership_tier} locale={locale} />
          <Badge tone="neutral">{storedUser ? `${storedUser.credit_balance ?? 0} credits` : t(locale, "common.topbar.credits")}</Badge>
          <LanguageSwitcher compact />
          <AppearanceControls locale={locale} />
          {storedUser ? (
            <Link href={withLocale(locale, "/account")} className="ml-2 flex items-center gap-2 border border-border-pg bg-bg-panel-muted px-2 py-1 hover:border-border-pg-strong rounded-lg">
              {storedUser.avatar_url ? <span aria-hidden className="h-5 w-5 rounded-full bg-cover bg-center" style={{ backgroundImage: `url(${storedUser.avatar_url})` }} /> : null}
              {storedUser.auth_provider === "google" ? <Chrome className="h-3.5 w-3.5" aria-label="Google" /> : null}
              <span className="max-w-[140px] truncate">{storedUser.name || storedUser.email}</span>
            </Link>
          ) : (
            <>
              <Link href={withLocale(locale, "/signup")} className="ml-2 border border-border-pg-strong bg-pg-white px-3 py-1 text-xs font-semibold text-pg-black hover:bg-pg-white-soft rounded-lg">{t(locale, "common.nav.signup")}</Link>
              <Link href={withLocale(locale, "/login")} className="border border-border-pg px-3 py-1 text-xs text-text-pg hover:border-border-pg-strong rounded-lg">{t(locale, "common.nav.signin")}</Link>
            </>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3 text-xs text-text-pg-muted md:hidden">
          {storedUser ? null : (
            <>
              <Link href={withLocale(locale, "/signup")} className="border border-border-pg-strong bg-pg-white px-2.5 py-1 font-semibold text-pg-black hover:bg-pg-white-soft rounded-lg">{t(locale, "common.nav.signup")}</Link>
              <Link href={withLocale(locale, "/login")} className="border border-border-pg px-2.5 py-1 text-text-pg hover:border-border-pg-strong rounded-lg">{t(locale, "common.nav.signin")}</Link>
            </>
          )}
          <div className="flex items-center gap-1.5"><LanguageSwitcher compact /><AppearanceControls locale={locale} showFontScale={false} /></div>
        </div>
      </div>
    </header>
  );
}
