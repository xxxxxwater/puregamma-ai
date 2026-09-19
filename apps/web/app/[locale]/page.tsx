import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/puregamma";
import { LandingFooterRotator } from "@/components/landing-footer-rotator";
import { ModelUpgradePreview } from "@/components/model-upgrade";
import { JevTraderPreview } from "@/components/jev-trader-preview";
import { TradingArchitecture } from "@/components/trading-architecture";
import { getGatewayCatalog } from "@/lib/api";
import { flashAvailability } from "@/lib/model-catalog";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "landing");
}

export default async function LandingPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "landing");
  const modelCopy = getMessageNamespace(locale, "model-upgrade");
  // Server-rendered from the catalog this deployment actually serves, so the
  // green "published" tone can never outrun the Gateway itself.
  const catalog = await getGatewayCatalog(locale);
  const availability = flashAvailability(catalog);

  return (
    <div className="space-y-16 py-4">
      <section className="border border-border-pg bg-bg-panel p-6 md:p-10 rounded-2xl">
        <div className="flex flex-wrap items-center gap-4 border-b border-border-pg pb-5 text-sm">
          <div className="flex items-center gap-2 font-semibold"><Image src="/logo.png" alt="PureGamma" width={24} height={24} />PureGamma AI</div>
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-5 text-sm" data-testid="model-announcement">
          <Badge tone={availability.state === "available" ? "emerald" : "neutral"}>
            <span className="inline-flex items-center gap-1.5">{modelCopy.announcement}</span>
          </Badge>
          <span className="text-text-pg-muted">{modelCopy.announcementDetail}</span>
        </div>
        <div className="grid gap-10 py-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-end lg:py-14">
          <div>
            <Badge tone="neutral">{copy.hero.eyebrow}</Badge>
            <h1 className="mt-7 max-w-5xl text-4xl font-semibold tracking-normal md:text-6xl">{copy.hero.headline}</h1>
            <p className="mt-6 max-w-3xl text-base leading-7 text-text-pg-muted">{copy.hero.subheadline}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href={withLocale(locale, "/chat")} className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-3 text-sm font-semibold text-pg-black rounded-lg">
                {copy.hero.primaryCta} <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href={withLocale(locale, "/api")} className="inline-flex items-center gap-2 border border-border-pg px-4 py-3 text-sm font-semibold text-text-pg hover:border-border-pg-strong rounded-lg">
                {locale === "zh" ? "API 快速接入" : "API Quickstart"} <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href={withLocale(locale, "/pricing")} className="inline-flex items-center gap-2 border border-border-pg px-4 py-3 text-sm font-semibold text-text-pg hover:border-border-pg-strong rounded-lg">
                {locale === "zh" ? "查看定价" : "View pricing"} <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
          <TradingArchitecture locale={locale} />
        </div>
      </section>

      <ModelUpgradePreview locale={locale} catalog={catalog} />
      <JevTraderPreview locale={locale} />

      <LandingFooterRotator slides={copy.footerSlides} />
    </div>
  );
}
