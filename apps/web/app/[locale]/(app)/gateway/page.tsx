import type { Metadata } from "next";
import { GatewayConsole } from "@/components/gateway-console";
import { PageHeader } from "@/components/puregamma";
import { getGatewayDashboard, getGatewayKeys, getGatewayRequests, getGatewayUsage } from "@/lib/api";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return {
    title: "PureGamma AI API Gateway",
    description: locale === "zh" ? "OpenAI 兼容 API 密钥、用量与请求记录。" : "OpenAI-compatible API keys, usage, and request history."
  };
}

export default async function GatewayPage({ params }: { params: { locale: Locale } }) {
  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const [dashboard, keys, requests, usage] = await Promise.all([
    getGatewayDashboard(params.locale),
    getGatewayKeys(params.locale),
    getGatewayRequests(params.locale),
    getGatewayUsage(params.locale, { start: weekAgo.toISOString().slice(0, 19) + "+00:00", end: now.toISOString().slice(0, 19) + "+00:00", granularity: "day" })
  ]);
  const zh = params.locale === "zh";
  return <div className="space-y-5"><PageHeader eyebrow="PureGamma API" title={zh ? "AI API Gateway" : "AI API Gateway"} description={zh ? "管理 OpenAI 兼容 API 密钥、已确认价格下的使用量与请求记录。" : "Manage OpenAI-compatible keys, approved-price usage, and request history."} sectionNumber="10" /><GatewayConsole locale={params.locale} dashboard={dashboard} initialKeys={keys.keys} initialRequests={requests.requests} initialUsage={usage} /></div>;
}
