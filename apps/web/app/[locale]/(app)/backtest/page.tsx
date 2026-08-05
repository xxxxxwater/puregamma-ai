import type { Metadata } from "next";
import { BacktestLab } from "@/components/backtest-lab";
import Script from "next/script";
import { localizedMetadata } from "@/lib/metadata";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "backtest-lab");
}

export default function BacktestPage({ params }: { params: { locale: Locale } }) {
  return <><Script src="https://cdn.plot.ly/plotly-2.35.2.min.js" strategy="afterInteractive" /><BacktestLab locale={params.locale} /></>;
}
