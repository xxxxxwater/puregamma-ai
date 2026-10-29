import type { Metadata } from "next";
import { AdminLiveTradingConsole } from "@/components/admin-live-trading-console";
import { PageHeader } from "@/components/puregamma";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const zh = isLocale(params.locale) && params.locale === "zh";
  return {
    title: zh ? "实盘审阅 | PureGamma AI" : "LIVE review | PureGamma AI",
    description: zh ? "Kill Switch、用户实盘资格与对账异常审阅。" : "Kill switches, user LIVE eligibility and reconciliation exception review.",
  };
}

export default function AdminLiveTradingPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="LIVE control plane"
        title={zh ? "实盘审阅" : "LIVE review"}
        description={zh ? "启用或释放 Kill Switch、审批用户实盘资格、审阅对账异常。每项操作都需要原因并写入审计。" : "Engage or release kill switches, decide user LIVE eligibility and review reconciliation exceptions. Every action needs a reason and is audited."}
        sectionNumber="11"
      />
      <AdminLiveTradingConsole locale={params.locale} />
    </div>
  );
}
