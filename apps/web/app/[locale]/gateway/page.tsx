import type { Metadata } from "next";
import { GatewayConsole } from "@/components/gateway-console";
import { PageHeader } from "@/components/puregamma";
import { getGatewayDashboard, getGatewayKeys, getGatewayRequests } from "@/lib/api";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return {
    title: "PureGamma AI API Gateway",
    description: locale === "zh" ? "OpenAI 兼容 API 密钥、用量与请求记录。" : "OpenAI-compatible API keys, usage, and request history."
  };
}

export default async function GatewayPage({ params }: { params: { locale: Locale } }) {
  const [dashboard, keys, requests] = await Promise.all([getGatewayDashboard(params.locale), getGatewayKeys(params.locale), getGatewayRequests(params.locale)]);
  const zh = params.locale === "zh";
  return <div className="space-y-5"><PageHeader eyebrow="PureGamma API" title={zh ? "AI API Gateway" : "AI API Gateway"} description={zh ? "管理 OpenAI 兼容 API 密钥、已确认价格下的使用量与请求记录。" : "Manage OpenAI-compatible keys, approved-price usage, and request history."} sectionNumber="10" /><GatewayConsole locale={params.locale} dashboard={dashboard} initialKeys={keys.keys} initialRequests={requests.requests} /></div>;
}
