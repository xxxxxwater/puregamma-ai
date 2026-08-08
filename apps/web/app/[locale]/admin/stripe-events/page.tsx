import type { Metadata } from "next";
import Link from "next/link";
import { Badge, MetricCard, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { api } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

type StripeEventRow = {
  id: string;
  stripe_event_id?: string;
  event_type: string;
  processed: boolean;
  requires_manual_review?: boolean;
  error_message?: string | null;
  raw_payload_hash?: string;
  created_at?: string;
};

type StripeProductStatus = {
  mode: string;
  stripe_available: boolean;
  items: { plan_name: string; status: string; local?: { stripe_price_id?: string | null; monthly_price?: number | null } | null; stripe?: { stripe_price_id?: string | null; monthly_price?: number | null } | null }[];
};

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "admin", "/admin/stripe-events");
}

export default async function StripeEventsPage({ params, searchParams }: { params: { locale: Locale }; searchParams?: { event_type?: string; page?: string } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "admin");
  const [data, products] = await Promise.all([
    api<{ stripe_events: StripeEventRow[] }>("/admin/stripe-events", { fallback: { stripe_events: [] }, locale }),
    api<StripeProductStatus>("/admin/stripe/products", { fallback: { mode: "mock", stripe_available: false, items: [] }, locale })
  ]);
  const activeFilter = searchParams?.event_type || "all";
  const page = Math.max(1, Number(searchParams?.page || "1") || 1);
  const pageSize = 25;
  const filteredEvents = activeFilter === "all" ? data.stripe_events : data.stripe_events.filter((event) => event.event_type === activeFilter);
  const visibleEvents = filteredEvents.slice((page - 1) * pageSize, page * pageSize);
  const eventTypes = Array.from(new Set(data.stripe_events.map((event) => event.event_type))).sort();
  const manualReview = data.stripe_events.filter((event) => event.requires_manual_review).length;
  const processed = data.stripe_events.filter((event) => event.processed).length;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={locale === "zh" ? "Stripe Webhook 审计" : "Stripe Webhook Audit"}
        description={locale === "zh" ? "签名验证、幂等处理、人工审核和错误原因的只读审计视图。" : "Read-only audit view for signature-verified webhook processing, idempotency, manual review, and errors."}
        sectionNumber="08.1"
      />
      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard label={locale === "zh" ? "事件数" : "Events"} value={String(data.stripe_events.length)} detail={copy.details.webhookAudit} tone="info" />
        <MetricCard label={locale === "zh" ? "已处理" : "Processed"} value={String(processed)} detail="stripe_event_id" tone="emerald" />
        <MetricCard label={locale === "zh" ? "人工审核" : "Manual review"} value={String(manualReview)} detail="requires_manual_review" tone={manualReview ? "amber" : "neutral"} />
      </div>
      <ResearchCard>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-semibold">{locale === "zh" ? "Stripe 商品同步状态" : "Stripe Product Sync Status"}</h2>
          <Badge tone="neutral"><StatusDot tone={products.stripe_available ? "emerald" : "amber"} /> {products.mode}</Badge>
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {products.items.length ? products.items.map((item) => (
            <div key={item.plan_name} className="border border-border-pg bg-bg-panel-muted p-3 text-sm rounded-lg">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{item.plan_name}</span>
                <Badge tone="neutral"><StatusDot tone={item.status === "in_sync" ? "emerald" : item.status === "mismatch" ? "amber" : "neutral"} /> {item.status}</Badge>
              </div>
              <div className="mt-2 text-xs text-text-pg-muted">local: {item.local?.stripe_price_id || "none"}</div>
              <div className="mt-1 text-xs text-text-pg-muted">stripe: {item.stripe?.stripe_price_id || "none"}</div>
            </div>
          )) : <div className="text-sm text-text-pg-muted">{locale === "zh" ? "暂无 Stripe 商品状态。" : "No Stripe product status available."}</div>}
        </div>
      </ResearchCard>
      <ResearchCard>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">{copy.modules.stripeWebhookEvents}</h2>
          <div className="flex flex-wrap gap-2 text-xs">
            <Link className="border border-border-pg px-2 py-1 hover:border-border-pg-strong rounded-lg" href={withLocale(locale, "/admin/stripe-events")}>all</Link>
            {eventTypes.slice(0, 8).map((eventType) => (
              <Link key={eventType} className="border border-border-pg px-2 py-1 hover:border-border-pg-strong rounded-lg" href={`${withLocale(locale, "/admin/stripe-events")}?event_type=${encodeURIComponent(eventType)}`}>{eventType}</Link>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          {visibleEvents.length ? visibleEvents.map((event) => (
            <div key={event.id} className="grid gap-2 border border-border-pg bg-bg-panel-muted p-3 text-sm lg:grid-cols-[1.5fr_1fr_auto] rounded-lg">
              <div>
                <div className="font-medium">{event.event_type}</div>
                <div className="mt-1 text-xs text-text-pg-muted">{event.stripe_event_id || event.id}</div>
              </div>
              <div className="text-xs text-text-pg-muted">
                <div>{event.created_at || "pending timestamp"}</div>
                {event.raw_payload_hash ? <div className="mt-1 break-all">sha256:{event.raw_payload_hash.slice(0, 20)}...</div> : null}
              </div>
              <div className="flex flex-wrap items-start gap-2 lg:justify-end">
                <Badge tone="neutral"><StatusDot tone={event.requires_manual_review ? "amber" : event.processed ? "emerald" : "neutral"} /> {event.requires_manual_review ? "manual review" : event.processed ? "processed" : "pending"}</Badge>
                {event.error_message ? <span className="w-full text-xs text-status-warning lg:text-right">{event.error_message}</span> : null}
              </div>
            </div>
          )) : <div className="text-sm text-text-pg-muted">{copy.details.noWebhookEvents}</div>}
        </div>
        <div className="mt-3 text-xs text-text-pg-muted">{locale === "zh" ? "当前显示" : "Showing"} {visibleEvents.length} / {filteredEvents.length}</div>
      </ResearchCard>
    </div>
  );
}
