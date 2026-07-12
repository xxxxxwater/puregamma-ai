import type { Metadata } from "next";
import { PageHeader } from "@/components/puregamma";
import { PortfolioConsole } from "@/components/portfolio-console";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "portfolio", "/portfolio");
}

export default async function PortfolioPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "portfolio");
  return (
    <div className="space-y-5">
      <PageHeader eyebrow={copy.eyebrow} title={copy.title} description={locale === "zh" ? "连接真实投资账户，统一复盘净值、可用资金与历史曲线。" : "Connect real investment accounts to review NAV, available capital, and history."} sectionNumber="02" />
      <PortfolioConsole locale={locale} />
    </div>
  );
}
