import type { Metadata } from "next";
import { Check } from "lucide-react";
import { BillingButton, PortalButton, SubscriptionLifecycleButton } from "@/components/actions";
import { CreditUsageChart } from "@/components/charts";
import { PGTable } from "@/components/pg-table";
import { Badge, CreditCostBadge, EmptyState, ErrorState, PageHeader, PlanBadge, ResearchCard, StatusDot } from "@/components/puregamma";
import { getBillingBudget, getBillingCredits, getBillingRewards, getBillingSubscription } from "@/lib/api";
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
  const [subscription, credits, budget, rewards] = await Promise.all([
    getBillingSubscription(locale),
    getBillingCredits(locale),
    getBillingBudget(locale),
    getBillingRewards(locale)
  ]);
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
      {subscription.unavailable || budget.unavailable || rewards.unavailable ? <ErrorState title={copy.billingUnavailable} description={copy.billingUnavailableDesc} /> : null}
      <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
        <ResearchCard>
          <div className="grid gap-4 md:grid-cols-5">
            <div><div className="text-sm text-text-pg-muted">{copy.summary.currentPlan}</div><div className="mt-2"><PlanBadge plan={subscription.plan} /></div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.subscription}</div><div className="mt-2"><Badge tone="neutral"><StatusDot tone={subscription.subscription_status === "past_due" ? "red" : "emerald"} /> {subscription.subscription_status}</Badge></div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.creditBalance}</div><div className="mt-2 text-2xl font-semibold">{subscription.credit_balance}</div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.periodEnd}</div><div className="mt-2 text-sm">{subscription.current_period_end ? formatDateTime(locale, subscription.current_period_end) : "-"}</div></div>
            <div><div className="text-sm text-text-pg-muted">{copy.summary.accountSource}</div><div className="mt-2 text-sm">{subscription.account?.auth_provider === "google" ? copy.accountSources.google : copy.accountSources.email}</div></div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 border-t border-border-pg pt-3 text-xs">
            {subscription.cancel_at_period_end && subscription.cancel_at ? <Badge tone="neutral"><StatusDot tone="amber" /> {copy.cancelAtPeriodEnd.replace("{date}", formatDateTime(locale, subscription.cancel_at))}</Badge> : null}
          </div>
          {subscription.subscription_status === "active" ? (
            <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border-pg pt-3">
              {subscription.cancel_at_period_end ? <SubscriptionLifecycleButton mode="reactivate" /> : <SubscriptionLifecycleButton mode="cancel" />}
              {!subscription.cancel_at_period_end ? <span className="text-xs text-text-pg-muted">{copy.cancelWarning}</span> : null}
            </div>
          ) : null}
        </ResearchCard>
        <ResearchCard>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.summary.creditUsage}</h2><CreditCostBadge locale={locale} cost={credits.credit_balance} /></div>
          {usageChart.length ? <CreditUsageChart data={usageChart} /> : <EmptyState title={copy.noUsage} description={copy.noUsageDesc} />}
        </ResearchCard>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ResearchCard>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="font-semibold">{copy.budgetsTitle}</h2>
            <Badge tone="neutral">{copy.hardStop}</Badge>
          </div>
          {budget.budgets.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[580px] text-sm">
                <thead className="text-left text-xs uppercase tracking-[0.1em] text-text-pg-muted"><tr><th className="py-2">{copy.automation}</th><th>{copy.thisMonth}</th><th>{copy.nextEstimate}</th><th>{copy.status}</th></tr></thead>
                <tbody>{budget.budgets.map((item) => <tr key={item.automation_key} className="border-t border-border-pg"><td className="py-3">{item.automation_key}</td><td>{item.monthly_used} / {item.monthly_limit}</td><td>{item.next_estimated_credits ?? "—"} Credits</td><td><Badge tone={item.paused || !item.enabled ? "amber" : "emerald"}><StatusDot tone={item.paused || !item.enabled ? "amber" : "emerald"} />{item.paused ? copy.paused : item.enabled ? copy.active : copy.disabled}</Badge></td></tr>)}</tbody>
              </table>
            </div>
          ) : <EmptyState title={copy.noBudgets} description={copy.noBudgetsDesc} />}
        </ResearchCard>
        <ResearchCard>
          <h2 className="mb-3 font-semibold">{copy.rewardHistory}</h2>
          {rewards.rewards.length ? (
            <div className="space-y-2">{rewards.rewards.slice(0, 8).map((item) => <div key={item.id} className="flex items-center justify-between gap-3 border-t border-border-pg py-2 text-sm"><div><div>{item.reward_type}</div><div className="text-xs text-text-pg-muted">{item.source} · {formatDateTime(locale, item.created_at)}</div></div><span className="text-status-positive">+{item.credits}</span></div>)}</div>
          ) : <EmptyState title={copy.noRewards} description={copy.noRewardsDesc} />}
        </ResearchCard>
      </div>
      <ResearchCard className="p-0">
        <div className="border-b border-border-pg p-4"><h2 className="font-semibold">{copy.valueTitle}</h2></div>
        <div className="grid gap-px bg-border-pg sm:grid-cols-2 xl:grid-cols-4">{copy.valueProps.map((item) => <div key={item.title} className="bg-bg-panel p-4"><div className="text-sm font-semibold">{item.title}</div><p className="mt-2 text-xs leading-5 text-text-pg-muted">{item.detail}</p></div>)}</div>
      </ResearchCard>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {copy.plans.map((plan) => (
          <ResearchCard key={plan.name} className={`flex flex-col ${plan.name === "Pro" || plan.name === "Max" ? "border-border-pg-strong" : ""}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">{plan.name}</h2>
                <div className="mt-2 text-2xl font-semibold">{plan.price}<span className="text-sm font-normal text-text-pg-muted">{copy.featureLabels.perMonth}</span></div>
              </div>
              {subscription.plan === plan.name ? <Badge tone="neutral"><StatusDot tone="emerald" /> {t(locale, "common.badges.active")}</Badge> : null}
            </div>
            <div className="mt-3 text-sm text-text-pg-muted">{plan.credits} {copy.creditsPerMonth}</div>
            <p className="mt-3 min-h-10 text-xs leading-5 text-text-pg-muted">{plan.tagline}</p>
            <ul className="mt-4 flex-1 space-y-2 border-t border-border-pg pt-4 text-sm">{plan.benefits.map((item) => <li key={item} className="flex gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-positive" /><span>{item}</span></li>)}</ul>
            <div className="mt-6">
              {plan.name === "Pro" || plan.name === "Max" || plan.name === "Enterprise" ? (
                <BillingButton
                  plan={plan.name as "Pro" | "Max" | "Enterprise"}
                  checkoutMode={subscription.checkout_mode === "payment_link" && !subscription.payment_links[plan.name] ? "session" : subscription.checkout_mode}
                  billingMode={subscription.billing_mode}
                  disabled={false}
                  disabledMessage={copy.paymentLinkMissing}
                />
              ) : <Badge>{t(locale, "common.badges.default")}</Badge>}
            </div>
          </ResearchCard>
        ))}
      </div>
      <p className="border border-border-pg bg-bg-panel-muted p-3 text-xs text-text-pg-muted rounded-lg">{copy.noPerformancePromise}</p>
      <ResearchCard>
        <h2 className="mb-3 font-semibold">{copy.summary.usageHistory}</h2>
        <PGTable columns={[{ key: "action", header: copy.usageTable.action, render: (item: typeof credits.usage_history[number]) => item.action }, { key: "delta", header: copy.usageTable.delta, render: (item: typeof credits.usage_history[number]) => <span className={item.credits_delta > 0 ? "text-status-positive" : "text-status-negative"}>{item.credits_delta}</span> }, { key: "balance", header: copy.usageTable.balanceAfter, render: (item: typeof credits.usage_history[number]) => item.balance_after }, { key: "created", header: copy.usageTable.created, render: (item: typeof credits.usage_history[number]) => formatDateTime(locale, item.created_at) }]} rows={credits.usage_history} />
      </ResearchCard>
    </div>
  );
}
