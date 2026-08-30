import type { Metadata } from "next";
import { LiveTradingConsole } from "@/components/live-trading-console";
import { isLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const zh = isLocale(params.locale) && params.locale === "zh";
  return {
    title: zh ? "实盘订单 | PureGamma AI" : "LIVE Orders | PureGamma AI",
    description: zh ? "预览 → 确认两步下单、风控检查结果、订单与撤单。" : "Two-step preview → confirm orders, risk check results, order list and cancellation.",
  };
}

export default function LiveTradingOrdersPage({ params }: { params: { locale: string } }) {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return <LiveTradingConsole locale={locale} view="orders" />;
}
