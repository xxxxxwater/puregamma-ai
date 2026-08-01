import type { Metadata } from "next";
import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "Paper 策略运行 | PureGamma AI" : "Paper Strategy Runtime | PureGamma AI", description: zh ? "模拟执行的策略运行状态、行情源与订单。" : "Paper-executed strategy runs, market feed, and orders." };
}

export default function PaperPage({ params }: { params: { locale: Locale } }) { return <StrategyRuntimeConsole locale={params.locale} view="paper" />; }
