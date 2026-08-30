import type { Metadata } from "next";
import { LiveTradingConsole } from "@/components/live-trading-console";
import { isLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const zh = isLocale(params.locale) && params.locale === "zh";
  return {
    title: zh ? "实盘总览 | PureGamma AI" : "LIVE Trading Overview | PureGamma AI",
    description: zh ? "实盘安全门、服务端 NAV、券商连接与熔断开关状态。" : "LIVE trading gates, server NAV, broker connections, and kill switch status.",
  };
}

export default function LiveTradingOverviewPage({ params }: { params: { locale: string } }) {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return <LiveTradingConsole locale={locale} view="overview" />;
}
