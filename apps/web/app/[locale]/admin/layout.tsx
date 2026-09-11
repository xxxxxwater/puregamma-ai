"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AdminGate } from "@/components/admin-gate";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { stripLocale, withLocale } from "@/i18n/routing";

/**
 * Admin section frame: one access guard for every admin route, plus a local
 * section nav.
 *
 * The admin pages were only reachable by finding a card on `/admin` itself, and
 * each page repeated its own header. Grouping them here gives the section one
 * guard and one navigation, so an administrator always knows where they are and
 * what else exists.
 */

type AdminNavItem = { href: string; zh: string; en: string };

const GROUPS: Array<{ zh: string; en: string; items: AdminNavItem[] }> = [
  {
    zh: "运营",
    en: "Operations",
    items: [
      { href: "/admin", zh: "总览", en: "Overview" },
      { href: "/admin/gateway", zh: "API Gateway", en: "API Gateway" },
    ],
  },
  {
    zh: "计费",
    en: "Billing",
    items: [
      { href: "/admin/billing-intents", zh: "支付意图", en: "Payment intents" },
      { href: "/admin/stripe-events", zh: "Stripe 事件", en: "Stripe events" },
    ],
  },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const locale = useLocale();
  const zh = locale === "zh";
  const activePath = stripLocale(usePathname() || "");

  return (
    <AdminGate>
      <div className="space-y-5">
        <nav aria-label={zh ? "管理后台分区" : "Admin sections"} className="border border-border-pg bg-bg-panel p-3 rounded-xl">
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            {GROUPS.map((group) => (
              <div key={group.en} className="min-w-0">
                <div className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim">{zh ? group.zh : group.en}</div>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {group.items.map((item) => {
                    const active = activePath === item.href;
                    return (
                      <li key={item.href}>
                        <Link
                          href={withLocale(locale, item.href)}
                          aria-current={active ? "page" : undefined}
                          className={`inline-flex min-h-9 items-center border px-2.5 text-xs transition rounded-lg ${
                            active
                              ? "border-border-pg-strong bg-bg-panel-muted font-semibold text-text-pg"
                              : "border-border-pg text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"
                          }`}
                        >
                          {zh ? item.zh : item.en}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </nav>
        {children}
      </div>
    </AdminGate>
  );
}
