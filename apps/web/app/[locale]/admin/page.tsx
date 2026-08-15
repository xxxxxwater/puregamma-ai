import type { Metadata } from "next";
import Link from "next/link";
import { AdminCreditConsole } from "@/components/admin-credit-console";
import { Badge, DataSourceStatusBadge, ErrorState, MetricCard, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { api, fallbackDataSourcesForLocale, fallbackSignalsForLocale } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

function maskEmail(email: string) {
  const [local, domain = "masked"] = email.split("@");
  const maskedLocal = local.length <= 2 ? `${local[0] || "*"}***` : `${local.slice(0, 2)}***`;
  const domainParts = domain.split(".");
  const maskedDomain = domainParts.length > 1 ? `****.${domainParts.slice(1).join(".")}` : "****";
  return `${maskedLocal}@${maskedDomain}`;
}

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "admin", "/admin");
}

export default async function AdminPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "admin");
  const [users, reports, stripeEvents, notifications, billingIntents, llmStatus] = await Promise.all([
    api<{ users: { id: string; email: string; plan: string; role: string; membership_tier: string }[]; unauthorized?: boolean }>("/admin/users", { fallback: { users: [{ id: "mock-admin", email: "demo@puregamma.ai", plan: "Free", role: "admin", membership_tier: "gold" }], unauthorized: true }, locale }),
    api<{ reports: { id: string; title: string; report_type: string }[] }>("/admin/reports", { fallback: { reports: [] }, locale }),
    api<{ stripe_events: { id: string; event_type: string; processed: boolean; requires_manual_review?: boolean; error_message?: string | null }[] }>("/admin/stripe-events", { fallback: { stripe_events: [] }, locale }),
    api<{ notifications: { id: string; channel: string; status: string }[] }>("/admin/notifications", { fallback: { notifications: [] }, locale }),
    api<{ billing_intents: { id: string; public_reference: string; plan_name: string; checkout_mode: string; status: string; metadata?: Record<string, unknown> }[] }>("/admin/billing-intents", { fallback: { billing_intents: [] }, locale }),
    api<{ provider: string; active_provider: string; model: string; configured: boolean; status: string; last_error?: string | null }>("/admin/llm-status", { fallback: { provider: "mock", active_provider: "mock", model: "mock-model", configured: true, status: "mock" }, locale })
  ]);
  const dataSources = fallbackDataSourcesForLocale(locale);
  const signals = fallbackSignalsForLocale(locale);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="08"
      />
      <ResearchCard className="border-border-pg-strong bg-bg-panel-muted"><p className="text-sm text-text-pg-muted">{copy.sensitiveNotice}</p></ResearchCard>
      {users.unauthorized ? <ErrorState title={copy.unauthorizedTitle} description={copy.unauthorizedDescription} /> : null}
      <AdminCreditConsole locale={locale} />
      <ResearchCard className="flex flex-wrap items-center justify-between gap-3">
        <div><div className="text-eyebrow uppercase text-text-pg-muted">PureGamma API</div><h2 className="mt-1 font-semibold">{locale === "zh" ? "API Gateway 管理" : "API Gateway administration"}</h2><p className="mt-1 text-sm text-text-pg-muted">{locale === "zh" ? "管理 Provider、价格审批、用户访问和消费限额。" : "Manage providers, price approvals, user access, and spend limits."}</p></div>
        <Link href={withLocale(locale, "/admin/gateway")} className="border border-border-pg bg-pg-white px-3 py-2 text-sm font-semibold text-pg-black rounded-lg">{locale === "zh" ? "打开管理台" : "Open console"}</Link>
      </ResearchCard>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label={copy.modules.users} value={String(users.users.length)} detail={copy.details.maskedAuditView} tone="info" />
        <MetricCard label={copy.modules.reports} value={String(reports.reports.length)} detail={copy.details.generatedResearch} tone="emerald" />
        <MetricCard label={copy.modules.signals} value={String(signals.signals.length)} detail={copy.details.activeBoard} tone="emerald" />
        <MetricCard label={copy.modules.stripeWebhookEvents} value={String(stripeEvents.stripe_events.length)} detail={copy.details.webhookAudit} tone="amber" />
        <MetricCard label={copy.modules.workerQueue} value="idle" detail="APScheduler/Celery" tone="neutral" />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.users}</h2><div className="space-y-2">{users.users.map((user, index) => <div key={user.id} className="grid gap-3 border border-border-pg bg-bg-panel-muted p-3 text-sm md:grid-cols-[42px_1fr_auto] rounded-lg"><span className="text-text-pg-dim">{String(index + 1).padStart(2, "0")}</span><span>{maskEmail(user.email)}</span><div className="flex gap-2"><Badge>{user.role}</Badge><Badge tone="neutral">{user.plan}</Badge><Badge tone={user.membership_tier === "gold" ? "amber" : "neutral"}>{user.membership_tier}</Badge></div></div>)}</div></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.subscriptions}</h2><div className="grid gap-2 text-sm"><div className="border border-border-pg bg-bg-panel-muted p-3 rounded-lg"><Badge tone="neutral"><StatusDot tone="amber" /> {copy.details.mockSubscriptionMirror}</Badge><p className="mt-2 text-text-pg-muted">{copy.details.subscriptionRecords}</p></div><div className="border border-border-pg bg-bg-panel-muted p-3 text-text-pg-muted rounded-lg">{copy.details.sensitiveMasked}</div></div></ResearchCard>
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.dataSourceStatus}</h2><div className="space-y-2">{dataSources.sources.slice(0, 8).map((source) => <div key={source.source} className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-2 text-sm rounded-lg"><span>{source.source}</span><DataSourceStatusBadge locale={locale} status={source.status} /></div>)}</div></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.stripeWebhookEvents}</h2><div className="space-y-2">{stripeEvents.stripe_events.length ? stripeEvents.stripe_events.map((event) => <div key={event.id} className="grid gap-2 border border-border-pg bg-bg-panel-muted p-2 text-sm rounded-lg"><div className="flex items-center justify-between"><span>{event.event_type}</span><Badge tone="neutral"><StatusDot tone={event.requires_manual_review ? "amber" : event.processed ? "emerald" : "amber"} /> {event.requires_manual_review ? "manual review" : event.processed ? "processed" : "pending"}</Badge></div>{event.error_message ? <div className="text-xs text-status-warning">{event.error_message}</div> : null}</div>) : <span className="text-sm text-text-pg-muted">{copy.details.noWebhookEvents}</span>}</div></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.notificationDeliveries}</h2><div className="space-y-2">{notifications.notifications.length ? notifications.notifications.map((item) => <div key={item.id} className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-2 text-sm rounded-lg"><span>{item.channel}</span><Badge tone="neutral"><StatusDot tone={item.status === "sent" ? "emerald" : "amber"} /> {item.status}</Badge></div>) : <span className="text-sm text-text-pg-muted">{copy.details.noDeliveries}</span>}</div></ResearchCard>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ResearchCard><h2 className="mb-3 font-semibold">BillingCheckoutIntent</h2><div className="space-y-2">{billingIntents.billing_intents.length ? billingIntents.billing_intents.slice(0, 8).map((intent) => <div key={intent.id} className="grid gap-2 border border-border-pg bg-bg-panel-muted p-2 text-sm rounded-lg"><div className="flex items-center justify-between"><span>{intent.public_reference}</span><Badge tone="neutral"><StatusDot tone={intent.status === "requires_manual_review" ? "amber" : intent.status === "completed" ? "emerald" : "neutral"} /> {intent.status}</Badge></div><div className="text-xs text-text-pg-muted">{intent.checkout_mode} / {intent.plan_name}</div></div>) : <span className="text-sm text-text-pg-muted">No billing intents in mock state.</span>}</div></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">LLM Provider Status</h2><div className="grid gap-2 text-sm"><div className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-2 rounded-lg"><span>{llmStatus.provider}</span><Badge tone="neutral"><StatusDot tone={llmStatus.status === "healthy" ? "emerald" : "amber"} /> {llmStatus.status}</Badge></div><div className="border border-border-pg bg-bg-panel-muted p-2 text-text-pg-muted rounded-lg">active={llmStatus.active_provider} / model={llmStatus.model}</div>{llmStatus.last_error ? <div className="text-xs text-status-warning">{llmStatus.last_error}</div> : null}</div></ResearchCard>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.creditLedger}</h2><p className="text-sm text-text-pg-muted">{copy.details.creditLedgerCopy}</p><Badge tone="neutral"><StatusDot tone="emerald" /> {copy.details.ledgerIdempotent}</Badge></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.imessageRelay}</h2><Badge tone="neutral"><StatusDot tone="amber" /> {copy.details.mockProvider}</Badge><p className="mt-3 text-sm text-text-pg-muted">{copy.details.relayCopy}</p></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.workerQueue}</h2><Badge tone="neutral"><StatusDot tone="emerald" /> idle</Badge><p className="mt-3 text-sm text-text-pg-muted">{copy.details.workerCopy}</p></ResearchCard>
        <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.agentEvalStatus}</h2><Badge tone="neutral"><StatusDot tone="amber" /> {copy.details.mockEvalSuite}</Badge><p className="mt-3 text-sm text-text-pg-muted">{copy.details.agentEvalCopy}</p></ResearchCard>
      </div>
    </div>
  );
}
