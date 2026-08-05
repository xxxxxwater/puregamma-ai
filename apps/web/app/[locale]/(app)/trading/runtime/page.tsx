import type { Metadata } from "next";
import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "Runtime 运行状态 | PureGamma AI" : "Runtime Status | PureGamma AI", description: zh ? "Runtime 事件、风险检查与执行适配器状态。" : "Runtime events, risk checks, and execution adapter status." };
}

export default function RuntimePage({ params }: { params: { locale: Locale } }) { return <StrategyRuntimeConsole locale={params.locale} view="runtime" />; }
