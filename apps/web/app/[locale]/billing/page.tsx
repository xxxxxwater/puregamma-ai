import type { Metadata } from "next";
import { BillingButton, PortalButton, SubscriptionLifecycleButton } from "@/components/actions";
import { CreditUsageChart } from "@/components/charts";
import { Badge, CreditCostBadge, PageHeader, PlanBadge, ResearchCard, StatusDot } from "@/components/puregamma";
import { getBillingCredits, getBillingSubscription } from "@/lib/api";
import { formatDateTime } from "@/lib/formatters";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "billing", "/billing");
}

export default async function BillingPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "billing");
  const [subscription, credits] = await Promise.all([getBillingSubscription(locale), getBillingCredits(locale)]);
  const usageChart = credits.usage_history.slice(0, 8).map((item, index) => ({ date: String(index + 1), value: Math.abs(item.credits_delta) }));

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="07"
        actions={<PortalButton />}
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
        <ResearchCard>
          <div className="grid gap-4 md:grid-cols-5">
            <div><div className="text-sm text-text-pg-muted">{copy.summary.currentPlan}</div><div className="mt-2"><PlanBadge plan={subscription.plan} /></div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.subscription}</div><div className="mt-2"><Badge tone="neutral"><StatusDot tone={subscription.subscription_status === "past_due" ? "red" : "emerald"} /> {subscription.subscription_status}</Badge></div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.creditBalance}</div><div className="mt-2 text-2xl font-semibold">{subscription.credit_balance}</div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.periodEnd}</div><div className="mt-2 text-sm">{subscription.current_period_end ? formatDateTime(locale, subscription.current_period_end) : t(locale, "common.shared.mockMode")}</div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.accountSource}</div><div className="mt-2 text-sm">{subscription.account?.auth_provider === "google" ? copy.accountSources.google : copy.accountSources.email}</div></div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 border-t border-border-pg pt-3 text-xs">
            <Badge tone="neutral">{copy.summary.checkoutMode}: {subscription.checkout_mode === "payment_link" ? copy.checkoutModes.paymentLink : copy.checkoutModes.session}</Badge>
            {subscription.primary_payment_link_configured ? <Badge tone="neutral">{copy.summary.primaryPaymentLink}</Badge> : null}
            {subscription.cancel_at_period_end && subscription.cancel_at ? <Badge tone="neutral"><StatusDot tone="amber" /> {copy.cancelAtPeriodEnd.replace("{date}", formatDateTime(locale, subscription.cancel_at))}</Badge> : null}
          </div>
          {subscription.subscription_status === "active" ? (
            <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border-pg pt-3">
              {subscription.cancel_at_period_end ? <SubscriptionLifecycleButton mode="reactivate" /> : <SubscriptionLifecycleButton mode="cancel" />}
              {!subscription.cancel_at_period_end ? <span className="text-xs text-text-pg-muted">{copy.cancelWarning}</span> : null}
            </div>
          ) : null}
          <p className="mt-4 border-t border-border-pg pt-3 text-xs text-text-pg-dim">{t(locale, "compliance.subscription")}</p>
        </ResearchCard>
        <ResearchCard>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.summary.creditUsage}</h2><CreditCostBadge locale={locale} cost={credits.credit_balance} /></div>
          <CreditUsageChart data={usageChart.length ? usageChart : [{ date: "Demo", value: 10 }]} />
        </ResearchCard>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {copy.plans.map((plan) => (
          <ResearchCard key={plan.name} className={plan.name === "Max" || plan.name === "Enterprise" ? "border-border-pg-strong" : ""}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">{plan.name}</h2>
                <div className="mt-2 text-2xl font-semibold">{plan.price}<span className="text-sm font-normal text-text-pg-muted">{copy.featureLabels.perMonth}</span></div>
              </div>
              {subscription.plan === plan.name ? <Badge tone="neutral"><StatusDot tone="emerald" /> {t(locale, "common.badges.active")}</Badge> : null}
            </div>
            <div className="mt-3 text-sm text-text-pg-muted">{plan.credits} {locale === "zh" ? "Credits / 月" : "credits / month"}</div>
            <div className="mt-4 grid gap-3 border-t border-border-pg pt-4 text-sm">
              <div><div className="text-text-pg-dim">{copy.featureLabels.researchAccess}</div><div className="mt-1">{plan.research}</div></div>
              <div><div className="text-text-pg-dim">{copy.featureLabels.dataAccess}</div><div className="mt-1">{plan.data}</div></div>
              <div><div className="text-text-pg-dim">{copy.featureLabels.notificationAccess}</div><div className="mt-1">{plan.notifications}</div></div>
              <div><div className="text-text-pg-dim">{copy.featureLabels.strategyLabAccess}</div><div className="mt-1">{plan.strategy}</div></div>
            </div>
            <ul className="mt-4 space-y-2 border-t border-border-pg pt-4 text-sm text-text-pg-muted">{plan.restrictions.map((item) => <li key={item}>- {item}</li>)}</ul>
            <p className="mt-4 text-xs text-text-pg-dim">{t(locale, "compliance.subscription")}</p>
            <div className="mt-4">
              {plan.name === "Pro" || plan.name === "Max" || plan.name === "Enterprise" ? (
                <BillingButton
                  plan={plan.name as "Pro" | "Max" | "Enterprise"}
                  checkoutMode={subscription.checkout_mode}
                  disabled={subscription.checkout_mode === "payment_link" && !subscription.payment_links[plan.name]}
                  disabledMessage={copy.paymentLinkMissing}
                />
              ) : <Badge>{t(locale, "common.badges.default")}</Badge>}
            </div>
          </ResearchCard>
        ))}
      </div>
      <ResearchCard>
        <h2 className="mb-3 font-semibold">{copy.summary.usageHistory}</h2>
        <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-sm"><thead className="text-left text-xs uppercase tracking-[0.12em] text-text-pg-muted"><tr><th className="py-2">{copy.usageTable.action}</th><th>{copy.usageTable.delta}</th><th>{copy.usageTable.balanceAfter}</th><th>{copy.usageTable.created}</th></tr></thead><tbody>{credits.usage_history.map((item) => <tr key={item.id} className="border-t border-border-pg"><td className="py-3">{item.action}</td><td className={item.credits_delta > 0 ? "text-status-positive" : "text-status-negative"}>{item.credits_delta}</td><td>{item.balance_after}</td><td>{formatDateTime(locale, item.created_at)}</td></tr>)}</tbody></table></div>
      </ResearchCard>
    </div>
  );
}
