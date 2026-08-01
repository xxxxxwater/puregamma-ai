import Link from "next/link";
import { PageHeader, ResearchCard } from "@/components/puregamma";
import { type Locale, withLocale } from "@/i18n/routing";


export function generateMetadata({ params }: { params: { locale: string } }) {
  const locale = params.locale === "zh" ? "zh" : "en";
  return { title: locale === "zh" ? "支付成功 | PureGamma AI" : "Payment Successful | PureGamma AI", description: locale === "zh" ? "订阅与充值支付成功确认。" : "Subscription and top-up payment confirmation." };
}

export default function BillingSuccessPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="STRIPE CHECKOUT" title={zh ? "付款处理中" : "Payment pending confirmation"} description={zh ? "付款已收到。订阅状态会在 Stripe Webhook 确认后更新。" : "Payment received. Your subscription will update after Stripe webhook confirmation."} />
      <ResearchCard>
        <p>{zh ? "PureGamma 不会仅凭 success URL 升级账户；最终套餐、Credits 与权限以 Stripe Webhook 验签后的结果为准。" : "PureGamma does not upgrade an account from the success URL alone; plan, credits, and entitlement update only after signed Stripe webhook confirmation."}</p>
        <Link className="mt-4 inline-flex text-sm font-medium underline" href={withLocale(params.locale, "/billing")}>{zh ? "返回订阅页" : "Back to billing"}</Link>
      </ResearchCard>
    </div>
  );
}
