"use client";

import Link from "next/link";
import Image from "next/image";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Bell, BookOpen, Bot, BrainCircuit, BriefcaseBusiness, Chrome, Code2, CreditCard, FlaskConical, Gauge, HeartHandshake, LayoutDashboard, LifeBuoy, Menu, MessageCircle, Network, Newspaper, Radar, Smartphone, UserRound, X, type LucideIcon } from "lucide-react";
import { AppearanceControls } from "@/components/appearance-controls";
import { PlanBadge, Badge } from "@/components/puregamma";
import { LanguageSwitcher } from "@/components/i18n/LanguageSwitcher";
import { LocaleProvider } from "@/components/i18n/LocaleProvider";
import type { Locale } from "@/i18n/routing";
import { stripLocale, withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";
import type { TranslationKey } from "@/lib/translations";
import { getMe, AUTH_EXPIRED_EVENT } from "@/lib/api";
import { formatClockTime, formatUtcTime, useClockNow } from "@/lib/chrono";
import { publishUserState, USER_STATE_EVENT, type SessionUserState } from "@/lib/user-state";
import { applySurfaceTier, surfaceTierForPath } from "@/lib/visual-style";
import { Chronosphere } from "@/components/chrono/chronosphere";
import { PluginRuntime } from "@/plugins/core/runtime";
import { usePluginNavItems } from "@/plugins/core/services/navigation";

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
      { href: "/news", labelKey: "common.nav.news", icon: Newspaper },
      { href: "/chat", labelKey: "common.nav.chat", icon: Bot },
      { href: "/research", labelKey: "common.nav.research", icon: FlaskConical },
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
      { href: "/jev-trader", labelKey: "common.nav.jevTrader", icon: Radar },
      { href: "/memory", labelKey: "common.nav.memory", icon: BrainCircuit },
      { href: "/mobile-access", labelKey: "common.nav.mobileAccess", icon: Smartphone },
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

/**
 * Nav items registered by Cordis plugins (currently the LIVE trading
 * console). Disabled items are honest placeholders — a plugin may advertise
 * a surface the server has not enabled, and that must read as "not enabled",
 * never as a fake working entry.
 */
function PluginNavSection({ locale, onNavigate }: { locale: Locale; onNavigate?: () => void }) {
  const items = usePluginNavItems();
  const pathname = usePathname();
  if (!items.length) return null;
  const activePathname = stripLocale(pathname);
  return (
    <div>
      <div className="mb-2 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-text-pg-dim">{t(locale, "common.nav.groups.trading")}</div>
      <div className="space-y-1">
        {items.map((item) => {
          const label = item.labelKey ? t(locale, item.labelKey) : item.label;
          const active = activePathname.startsWith(item.href);
          if (item.disabled) {
            return (
              <span key={item.href} aria-disabled="true" title={label} className="flex cursor-not-allowed items-center gap-2 border border-transparent px-3 py-2 text-sm text-text-pg-dim opacity-70">
                {label}
              </span>
            );
          }
          return (
            <Link key={item.href} href={withLocale(locale, item.href)} onClick={onNavigate} aria-current={active ? "page" : undefined} className={`nav-item ${active ? "nav-active" : ""}`}>
              {label}
            </Link>
          );
        })}
      </div>
    </div>
  );
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
  // Route-derived surface tier for the glass visual system: financial/security
  // pages get higher-opacity panels, Ocean pages skip the extra blur. The
  // attribute lives on <html> so CSS tokens can scope it; remove it when the
  // shell unmounts (non-locale pages have no shell).
  useEffect(() => {
    applySurfaceTier(surfaceTierForPath(pathname || "/"));
    return () => applySurfaceTier(null);
  }, [pathname]);
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
      <PluginRuntime>
        <div className="relative min-h-screen">
          <Chronosphere />
          <AuthExpiredRedirector locale={locale} />
        <SidebarNav locale={locale} />
        <MobileNavDrawer locale={locale} open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

        <div className="lg:pl-[284px]">
          <TopStatusBar locale={locale} onMenuClick={() => setMobileNavOpen(true)} />

            <main className="mx-auto max-w-[1440px] px-4 py-5 md:px-6">
              {children}
            </main>
          </div>
        </div>
      </PluginRuntime>
    </LocaleProvider>
  );
}

export function MobileNavDrawer({ locale, open, onClose }: { locale: Locale; open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const activePathname = stripLocale(pathname);
  return (
    <>
      {open ? <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden" onClick={onClose} aria-hidden /> : null}
      <div role="dialog" aria-modal="true" aria-label={locale === "zh" ? "主导航" : "Primary navigation"} className={`fixed inset-y-3 left-3 z-50 flex w-80 max-w-[85vw] transform flex-col rounded-2xl border border-border-pg bg-bg-app p-5 shadow-2xl transition-transform duration-200 lg:hidden ${open ? "translate-x-0" : "-translate-x-full"}`}>
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
                    <Link key={item.href} href={withLocale(locale, item.href)} onClick={onClose} aria-current={active ? "page" : undefined} className={`nav-item ${active ? "nav-active" : ""}`}>
                      <Icon className="nav-icon" aria-hidden />
                      {t(locale, item.labelKey)}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
          <PluginNavSection locale={locale} onNavigate={onClose} />
        </nav>
        <Link href={withLocale(locale, "/account#imessage-bind")} onClick={onClose} className="flex items-center gap-2 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg">
          <MessageCircle className="h-4 w-4" aria-hidden />
          {locale === "zh" ? "绑定 iMessage" : "Bind iMessage"}
        </Link>
        {/*
          Language and appearance moved here from the small-screen header.

          They were removed from the top bar because that row also held the
          wordmark, and the flex algorithm resolved the competition by
          compressing the brand to 65px — the brand lost and the secondary
          controls won. Keeping them reachable (rather than deleting them) is
          what makes that a layout fix instead of a feature removal. This block
          is hidden from `md` up, where the top bar has room for them again.
        */}
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-border-pg pt-3 md:hidden" data-testid="nav-secondary-controls">
          <span className="text-xs text-text-pg-dim">
            {locale === "zh" ? "显示与外观" : "Display & appearance"}
          </span>
          <div className="flex items-center gap-1.5">
            <LanguageSwitcher compact />
            <AppearanceControls locale={locale} showFontScale={false} />
          </div>
        </div>
      </div>
    </>
  );
}

export function SidebarNav({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const activePathname = stripLocale(pathname);
  return (
    <aside className="shell-rail hidden flex-col p-4 lg:flex">
      <Link href={withLocale(locale, "/")} className="flex items-center gap-2.5"><Image src="/logo.png" alt="PureGamma" width={22} height={22} /><span className="text-[0.95rem] font-semibold tracking-tight text-text-pg">PureGamma</span><span className="mt-0.5 text-[0.6rem] font-medium uppercase tracking-[0.3em] text-text-pg-dim">AI</span>
      </Link>
      <div className="mt-2 text-sm leading-6 text-text-pg-muted">{t(locale, "common.nav.tagline")}</div>
      <div className="mt-4">
        <div className="flex items-center gap-2"><LanguageSwitcher compact /><AppearanceControls locale={locale} /></div>
      </div>
      <nav className="shell-nav mt-8 flex-1 space-y-7 overflow-y-auto pr-1">
        {groups.map((group) => (
          <div key={group.labelKey}>
            <div className="mb-2 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-text-pg-dim">{t(locale, group.labelKey)}</div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.href === "/" ? activePathname === "/" : activePathname.startsWith(item.href);
                return (
                  <Link key={item.href} href={withLocale(locale, item.href)} className={`nav-item ${active ? "nav-active" : ""}`}>
                    <Icon className="nav-icon" aria-hidden />
                    {t(locale, item.labelKey)}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
        <PluginNavSection locale={locale} />
      </nav>
      <Link href={withLocale(locale, "/account#imessage-bind")} className="mt-3 flex shrink-0 items-center gap-2 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg">
        <MessageCircle className="h-4 w-4" aria-hidden />
        {locale === "zh" ? "绑定 iMessage" : "Bind iMessage"}
      </Link>
    </aside>
  );
}

export function TopStatusBar({ locale, onMenuClick }: { locale: Locale; onMenuClick: () => void }) {
  const [storedUser, setStoredUser] = useState<StoredUser | null>(null);
  const pathname = usePathname();
  const dashboardRoute = stripLocale(pathname || "/") === "/dashboard";
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
    <header className="shell-chrome">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-2 px-3 py-2.5 sm:gap-4 sm:px-5 sm:py-3">
        {/*
          Small-screen header order: menu, BRAND, primary action.
          The brand sits second and is allowed to keep its natural width
          (`shrink-0`). It used to be the only shrinkable item in a row that also
          held the language switcher and four appearance buttons, so at 390px the
          flex algorithm squeezed it to 65px and the wordmark rendered as
          "PureG…" — the brand was unreadable on the device most visitors use.
          The fix is to stop competing for that space: the language switcher and
          appearance controls moved into the drawer, where they are still
          reachable, and the brand is no longer compressible. Font size was not
          reduced to make things fit.
        */}
        <button type="button" onClick={onMenuClick} aria-label={locale === "zh" ? "打开导航" : "Open navigation"} className="grid h-9 w-9 shrink-0 place-items-center border border-border-pg text-text-pg-muted hover:border-border-pg-strong lg:hidden rounded-lg" data-testid="nav-menu-button"><Menu className="h-4 w-4" /></button>
        <Link
          href={withLocale(locale, "/")}
          className="flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-text-pg lg:hidden"
          data-testid="nav-brand"
        >
          <Image src="/logo.png" alt="" width={20} height={20} />
          <span>PureGamma AI</span>
          <span className="sr-only">{locale === "zh" ? "，返回首页" : ", back to home"}</span>
        </Link>
        <div className="hidden items-center gap-2 text-xs md:flex">
          {!dashboardRoute ? <TopClock locale={locale} /> : null}
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
              <Link href={withLocale(locale, "/signup")} className="ml-2 border border-border-pg-strong bg-[var(--pg-surface-inverse)] px-3 py-1 text-xs font-semibold text-[var(--pg-text-inverse)] rounded-lg">{t(locale, "common.nav.signup")}</Link>
              <Link href={withLocale(locale, "/login")} className="border border-border-pg px-3 py-1 text-xs text-text-pg hover:border-border-pg-strong rounded-lg">{t(locale, "common.nav.signin")}</Link>
            </>
          )}
        </div>
        {/* Only the primary action competes with the brand here; everything
            secondary lives in the drawer. */}
        <div className="flex shrink-0 items-center gap-2 text-xs text-text-pg-muted md:hidden">
          {storedUser ? null : (
            <Link href={withLocale(locale, "/signup")} className="whitespace-nowrap border border-border-pg-strong bg-[var(--pg-surface-inverse)] px-2.5 py-1 font-semibold text-[var(--pg-text-inverse)] rounded-lg">{t(locale, "common.nav.signup")}</Link>
          )}
        </div>
      </div>
    </header>
  );
}

function TopClock({ locale }: { locale: Locale }) {
  const now = useClockNow(1000);
  return (
    <span className="hidden items-center gap-2 whitespace-nowrap font-mono text-[0.68rem] tabular-nums text-text-pg-muted xl:inline-flex">
      <span aria-hidden className="status-dot status-dot-live" />
      {formatClockTime(now, locale === "zh" ? "zh-CN" : "en-US")}
      <span className="text-text-pg-dim">· UTC {formatUtcTime(now)}</span>
    </span>
  );
}
