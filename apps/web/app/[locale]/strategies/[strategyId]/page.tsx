import type { Metadata } from "next";
import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string; strategyId: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? `策略详情 ${params.strategyId} | PureGamma AI` : `Strategy ${params.strategyId} | PureGamma AI`, description: zh ? "策略版本详情、数据源与执行控制。" : "Strategy version details, sources, and execution controls." };
}

export default function StrategyDetailPage({ params }: { params: { locale: Locale; strategyId: string } }) { return <StrategyRuntimeConsole locale={params.locale} view="detail" strategyId={params.strategyId} />; }
