import type { Metadata } from "next";
import Link from "next/link";
import { Check } from "lucide-react";
import { Badge, PGResearchCard } from "@/components/puregamma";
import { localizedMetadata } from "@/lib/metadata";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "landing", "/pricing");
}

// Public pricing mirror of packages/billing/plans.py (single source of truth).
type PlanInfo = {
  id: string;
  priceZh: string;
  priceEn: string;
  creditsZh: string;
  creditsEn: string;
  featuresZh: string[];
  featuresEn: string[];
  ctaZh: string;
  ctaEn: string;
  invited?: boolean;
};

const PLANS: PlanInfo[] = [
  {
    id: "Free",
    priceZh: "$0",
    priceEn: "$0",
    creditsZh: "150 额度/月",
    creditsEn: "150 credits/mo",
    featuresZh: ["每日 1 份简报", "5 次 agent 运行/日", "10 条告警/月", "email + push 通知"],
    featuresEn: ["1 daily brief", "5 agent runs/day", "10 alerts/month", "email + push channels"],
    ctaZh: "免费开始",
    ctaEn: "Start free",
  },
  {
    id: "Invite Preview",
    priceZh: "$0",
    priceEn: "$0",
    creditsZh: "300 额度/月",
    creditsEn: "300 credits/mo",
    featuresZh: ["20 次 agent 运行/日", "50 条告警/月", "Telegram + email + push", "基础回测"],
    featuresEn: ["20 agent runs/day", "50 alerts/month", "Telegram, email, push", "Basic backtest"],
    ctaZh: "邀请制",
    ctaEn: "By invite",
    invited: true,
  },
  {
    id: "Pro",
    priceZh: "$29.90/月",
    priceEn: "$29.90/mo",
    creditsZh: "3000 额度/月",
    creditsEn: "3000 credits/mo",
    featuresZh: ["期权数据源", "50 次 agent 运行/日", "100 条告警/月", "Telegram + email + push"],
    featuresEn: ["Options data sources", "50 agent runs/day", "100 alerts/month", "Telegram, email, push"],
    ctaZh: "升级 Pro",
    ctaEn: "Upgrade to Pro",
  },
  {
    id: "Max",
    priceZh: "$199/月",
    priceEn: "$199/mo",
    creditsZh: "15000 额度/月",
    creditsEn: "15000 credits/mo",
    featuresZh: ["X / on-chain / Coinglass / Glassnode 数据", "200 次 agent 运行/日", "iMessage + Slack", "高级回测 + 私有 playbook"],
    featuresEn: ["X, on-chain, Coinglass, Glassnode", "200 agent runs/day", "iMessage + Slack", "Advanced backtest + private playbooks"],
    ctaZh: "升级 Max",
    ctaEn: "Upgrade to Max",
  },
  {
    id: "Enterprise",
    priceZh: "定制",
    priceEn: "Custom",
    creditsZh: "50000 额度/月起",
    creditsEn: "50000 credits/mo+",
    featuresZh: ["全部数据源 + API", "100 次简报/日", "10000 条告警/月", "专属支持"],
    featuresEn: ["All data sources + API", "100 reports/day", "10000 alerts/month", "Dedicated support"],
    ctaZh: "联系我们",
    ctaEn: "Contact us",
  },
];

export default function PricingPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return (
    <div className="space-y-12 py-4">
      <section className="border border-border-pg bg-bg-panel p-6 md:p-10 rounded-2xl">
        <Badge tone="neutral">{zh ? "订阅与额度" : "Subscriptions & credits"}</Badge>
        <h1 className="mt-6 text-3xl font-semibold md:text-4xl">{zh ? "按计划解锁研究能力" : "Unlock research depth by plan"}</h1>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-text-pg-muted">
          {zh
            ? "订阅控制权益，信用额度计量高成本研究动作。定价与额度不构成任何收益承诺。"
            : "Subscriptions control entitlements; credits meter high-cost research actions. Pricing never implies any return promise."}
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {PLANS.map((plan) => (
          <PGResearchCard key={plan.id} className="flex flex-col">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{plan.id}</h2>
              <Badge tone={plan.id === "Pro" ? "emerald" : "neutral"}>{plan.id === "Pro" ? (zh ? "推荐" : "Popular") : plan.id}</Badge>
            </div>
            <div className="mt-4 text-2xl font-semibold">{zh ? plan.priceZh : plan.priceEn}</div>
            <div className="mt-1 text-xs text-text-pg-muted">{zh ? plan.creditsZh : plan.creditsEn}</div>
            <ul className="mt-5 flex-1 space-y-2.5">
              {(zh ? plan.featuresZh : plan.featuresEn).map((feature) => (
                <li key={feature} className="flex items-start gap-2 text-xs leading-5 text-text-pg-muted">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-positive" />
                  {feature}
                </li>
              ))}
            </ul>
            {plan.invited ? (
              <span
                aria-disabled
                className={`mt-6 inline-flex cursor-not-allowed items-center justify-center border px-4 py-2.5 text-sm font-semibold rounded-lg border-border-pg text-text-pg-muted`}
              >
                {zh ? plan.ctaZh : plan.ctaEn}
              </span>
            ) : (
              <Link
                href={plan.id === "Enterprise" ? "mailto:hello@puregamma.ai" : withLocale(params.locale, "/billing")}
                className={`mt-6 inline-flex items-center justify-center border px-4 py-2.5 text-sm font-semibold rounded-lg ${plan.id === "Pro" || plan.id === "Max" ? "border-border-pg-strong bg-pg-white text-pg-black" : "border-border-pg text-text-pg hover:border-border-pg-strong"}`}
              >
                {zh ? plan.ctaZh : plan.ctaEn}
              </Link>
            )}
          </PGResearchCard>
        ))}
      </section>
    </div>
  );
}
