import type { Metadata } from "next";
import { AdminGate } from "@/components/admin-gate";
import { GatewayAdminConsole } from "@/components/gateway-admin-console";
import { PageHeader } from "@/components/puregamma";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const zh = isLocale(params.locale) && params.locale === "zh";
  return {
    title: zh ? "API Gateway 管理 | PureGamma AI" : "API Gateway Administration | PureGamma AI",
    description: zh
      ? "管理 Provider、官方价格审核、用户限额和 Gateway 用量。"
      : "Manage providers, official-price approvals, user limits, and Gateway usage.",
  };
}

export default function GatewayAdministrationPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return (
    <AdminGate>
      <div className="space-y-5">
        <PageHeader
          eyebrow="PureGamma API"
          title={zh ? "API Gateway 管理" : "API Gateway administration"}
          description={zh ? "审核官方价格、管理 Provider 健康状态，并设置用户访问和消费限额。" : "Review official pricing, manage Provider health, and set user access and spend limits."}
          sectionNumber="10"
        />
        <GatewayAdminConsole locale={params.locale} />
      </div>
    </AdminGate>
  );
}
