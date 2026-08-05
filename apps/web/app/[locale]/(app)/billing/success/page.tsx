import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { PageHeader, ResearchCard } from "@/components/puregamma";
import { type Locale, withLocale } from "@/i18n/routing";


export function generateMetadata({ params }: { params: { locale: string } }) {
  const locale = params.locale === "zh" ? "zh" : "en";
  return { title: locale === "zh" ? "支付成功 | PureGamma AI" : "Payment Successful | PureGamma AI", description: locale === "zh" ? "订阅与充值支付成功确认。" : "Subscription and top-up payment confirmation." };
}

export default function BillingSuccessPage({ params, searchParams }: { params: { locale: Locale }; searchParams?: { mode?: string } }) {
  const zh = params.locale === "zh";
  const mock = searchParams?.mode === "mock";
  if (mock) {
    return (
      <div className="space-y-5">
        <PageHeader eyebrow="MOCK CHECKOUT" title={zh ? "订阅已升级" : "Subscription upgraded"} description={zh ? "模拟结算是演示流程，不涉及真实扣费。" : "Mock checkout is a demo flow and never charges real money."} />
        <ResearchCard>
          <p className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-status-positive" />{zh ? "你的套餐与 Credits 已按模拟结算更新。" : "Your plan and credits were updated by the mock checkout."}</p>
          <Link className="mt-4 inline-flex text-sm font-medium underline" href={withLocale(params.locale, "/billing")}>{zh ? "返回订阅页" : "Back to billing"}</Link>
        </ResearchCard>
      </div>
    );
  }
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
