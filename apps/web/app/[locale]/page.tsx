import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BrandOrbit } from "@/components/brand-orbit";
import { Badge } from "@/components/puregamma";
import { LandingFooterRotator } from "@/components/landing-footer-rotator";
import { ModelUpgradePreview } from "@/components/model-upgrade";
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
    <div className="space-y-12 py-4 md:space-y-16">
      <section className="rounded-3xl border border-border-pg bg-bg-panel p-6 shadow-panel md:p-10 lg:p-12">
        <div className="flex flex-wrap items-center gap-3 text-sm" data-testid="model-announcement" data-model-availability={availability.state}>
          <Badge tone="neutral">
            <span className="inline-flex items-center gap-1.5">{availability.state === "available" ? modelCopy.announcement : `${locale === "zh" ? "Agent 默认模型" : "Agent default"} · ${modelCopy.modelName}`}</span>
          </Badge>
          <span className="text-text-pg-muted">{modelCopy.announcementDetail}</span>
          {availability.state !== "available" ? <Badge tone="neutral">{catalog && !catalog.gateway_enabled ? modelCopy.stateGatewayOff : availability.state === "unknown" ? modelCopy.stateUnverified : modelCopy.statePending}</Badge> : null}
        </div>
        <div className="grid gap-10 pb-5 pt-12 lg:grid-cols-[1.08fr_0.92fr] lg:items-center lg:pb-10 lg:pt-16">
          <div>
            <div className="section-eyebrow flex items-center gap-3"><span className="h-px w-5 bg-border-pg-strong" />{copy.hero.eyebrow}</div>
            <h1 className="mt-7 max-w-3xl font-display text-[clamp(2.7rem,5.4vw,5.5rem)] font-semibold leading-[0.99] tracking-[-0.065em] text-text-pg">{copy.hero.headline}</h1>
            <p className="mt-7 max-w-xl text-base leading-8 text-text-pg-muted">{copy.hero.subheadline}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href={withLocale(locale, "/chat")} className="inline-flex min-h-12 items-center gap-3 rounded-full border border-border-pg-strong bg-[var(--pg-surface-inverse)] px-5 py-3 text-sm font-semibold text-[var(--pg-text-inverse)] transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-card-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text-pg">
                {copy.hero.primaryCta} <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href={withLocale(locale, "/api")} className="inline-flex min-h-12 items-center gap-2 rounded-full border border-border-pg px-5 py-3 text-sm font-medium text-text-pg transition hover:border-border-pg-strong hover:bg-bg-panel-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text-pg">
                {locale === "zh" ? "API 快速接入" : "API Quickstart"} <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href={withLocale(locale, "/pricing")} className="inline-flex min-h-12 items-center gap-2 rounded-full border border-border-pg px-5 py-3 text-sm font-medium text-text-pg transition hover:border-border-pg-strong hover:bg-bg-panel-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text-pg">
                {locale === "zh" ? "查看定价" : "View pricing"} <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
          <BrandOrbit locale={locale} />
        </div>
      </section>

      <ModelUpgradePreview locale={locale} catalog={catalog} />

      <TradingArchitecture locale={locale} />

      <LandingFooterRotator slides={copy.footerSlides} />
    </div>
  );
}
