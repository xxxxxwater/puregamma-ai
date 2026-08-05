import Link from "next/link";
import { PageHeader, ResearchCard } from "@/components/puregamma";
import { type Locale, withLocale } from "@/i18n/routing";


export function generateMetadata({ params }: { params: { locale: string } }) {
  const locale = params.locale === "zh" ? "zh" : "en";
  return { title: locale === "zh" ? "支付已取消 | PureGamma AI" : "Payment Cancelled | PureGamma AI", description: locale === "zh" ? "支付流程已取消。" : "The payment flow was cancelled." };
}

export default function BillingCancelPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="STRIPE CHECKOUT" title={zh ? "订阅已取消" : "Billing cancelled"} description={zh ? "当前订阅与 Credit 权限保持不变。" : "Your subscription and credit entitlement remain unchanged."} />
      <ResearchCard>
        <p>{zh ? "Checkout 已取消。当前套餐保持不变。" : "Checkout was cancelled. Your existing plan remains unchanged."}</p>
        <Link className="mt-4 inline-flex text-sm font-medium underline" href={withLocale(params.locale, "/billing")}>{zh ? "返回订阅页" : "Back to billing"}</Link>
      </ResearchCard>
    </div>
  );
}
