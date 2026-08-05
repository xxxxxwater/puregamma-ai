import type { Metadata } from "next";
import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "策略版本 | PureGamma AI" : "Strategy Versions | PureGamma AI", description: zh ? "策略草稿、版本与激活确认。" : "Strategy drafts, versions, and activation confirmations." };
}

export default function StrategiesPage({ params }: { params: { locale: Locale } }) { return <StrategyRuntimeConsole locale={params.locale} view="strategies" />; }
