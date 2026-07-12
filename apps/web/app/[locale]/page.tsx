import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Badge, PGResearchCard } from "@/components/puregamma";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "landing");
}

export default function LandingPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "landing");

  return (
    <div className="space-y-16 py-4">
      <section className="border border-border-pg bg-bg-panel p-6 md:p-10">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-pg pb-5 text-sm">
          <div className="flex items-center gap-2 font-semibold"><img src="/logo.png" alt="PureGamma" className="h-6 w-6" />PureGamma AI</div>
          <div className="flex flex-wrap items-center gap-3">
            <Link href={withLocale(locale, "/login")} className="inline-flex items-center border border-border-pg px-4 py-2 text-sm font-semibold hover:border-border-pg-strong">{locale === "zh" ? "登录" : "Login"}</Link>
            <Link href={withLocale(locale, "/login")} className="inline-flex items-center border border-border-pg-strong bg-pg-white px-4 py-2 text-sm font-semibold text-pg-black">{locale === "zh" ? "注册" : "Sign Up"}</Link>
          </div>
        </div>
        <div className="grid gap-10 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:items-end">
          <div>
            <Badge tone="neutral">{copy.hero.eyebrow}</Badge>
            <h1 className="mt-7 max-w-5xl text-4xl font-semibold tracking-normal md:text-6xl">{copy.hero.headline}</h1>
            <p className="mt-6 max-w-3xl text-base leading-7 text-text-pg-muted">{copy.hero.subheadline}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href={withLocale(locale, "/chat")} className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-3 text-sm font-semibold text-pg-black">
                {copy.hero.primaryCta} <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
          <PGResearchCard>
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">{copy.engine.eyebrow}</div>
            <div className="mt-6 divide-y divide-border-pg border border-border-pg">
              {copy.engine.rows.map((row, index) => (
                <div key={row.label} className="grid grid-cols-[52px_1fr] gap-4 p-4">
                  <span className="text-text-pg-dim">{String(index + 1).padStart(2, "0")}</span>
                  <div><div className="font-semibold">{row.label}</div><div className="mt-1 text-sm text-text-pg-muted">{row.detail}</div></div>
                </div>
              ))}
            </div>
          </PGResearchCard>
        </div>
      </section>

      <section className="grid gap-px border border-border-pg bg-border-pg md:grid-cols-4">
        {copy.stats.map((item) => <div key={item} className="bg-bg-panel p-5 text-sm font-semibold">{item}</div>)}
      </section>

      <section id="research" className="grid gap-3 md:grid-cols-4">
        <PGResearchCard><div className="text-[0.68rem] uppercase tracking-[0.16em] text-text-pg-muted">{copy.research.eyebrow}</div><h2 className="mt-2 text-lg font-semibold">{copy.research.headline}</h2></PGResearchCard>
        {copy.research.cards.map((item) => <PGResearchCard key={item.title}><h3 className="text-sm font-semibold">{item.title}</h3><p className="mt-2 text-xs leading-5 text-text-pg-muted">{item.body}</p></PGResearchCard>)}
      </section>

      <footer className="border-t border-border-pg pt-5 text-xs text-text-pg-muted">{copy.footer}</footer>
    </div>
  );
}
