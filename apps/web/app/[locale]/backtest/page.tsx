import type { Metadata } from "next";
import { BacktestLab } from "@/components/backtest-lab";
import { localizedMetadata } from "@/lib/metadata";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "backtest-lab");
}

export default function BacktestPage({ params }: { params: { locale: Locale } }) {
  return <BacktestLab locale={params.locale} />;
}
