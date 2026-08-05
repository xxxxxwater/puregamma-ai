import type { Metadata } from "next";
import { AdminGate } from "@/components/admin-gate";
import { Badge, MetricCard, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { api } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

type BillingIntentRow = {
  id: string;
  public_reference: string;
  user_id: string;
  plan_name: string;
  checkout_mode: string;
  status: string;
  stripe_payment_link_url?: string | null;
  stripe_checkout_session_id?: string | null;
  stripe_price_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
  completed_at?: string | null;
};

function manualReviewReason(intent: BillingIntentRow) {
  const value = intent.metadata?.manual_review_reason;
  return typeof value === "string" ? value : undefined;
}

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "admin", "/admin/billing-intents");
}

export default async function BillingIntentsPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "admin");
  const data = await api<{ billing_intents: BillingIntentRow[] }>("/admin/billing-intents", {
    fallback: { billing_intents: [] },
    locale,
  });
  const manualReview = data.billing_intents.filter((intent) => intent.status === "requires_manual_review").length;
  const completed = data.billing_intents.filter((intent) => intent.status === "completed").length;

  return (
    <AdminGate>
      <div className="space-y-5">
        <PageHeader
          eyebrow={copy.eyebrow}
          title={locale === "zh" ? "BillingCheckoutIntent 审计" : "Billing Checkout Intent Audit"}
          description={locale === "zh" ? "Stripe Checkout Session 与 Payment Link 的统一 checkout intent、plan 映射和人工审核队列。" : "Unified checkout intent, plan mapping, and manual review queue for Stripe Checkout Sessions and Payment Links."}
          sectionNumber="08.2"
        />
      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard label={locale === "zh" ? "Intent 数" : "Intents"} value={String(data.billing_intents.length)} detail="BillingCheckoutIntent" tone="info" />
        <MetricCard label={locale === "zh" ? "已完成" : "Completed"} value={String(completed)} detail="completed_at" tone="emerald" />
        <MetricCard label={locale === "zh" ? "人工审核" : "Manual review"} value={String(manualReview)} detail="primary Payment Link guardrail" tone={manualReview ? "amber" : "neutral"} />
      </div>
      <ResearchCard>
        <h2 className="mb-3 font-semibold">BillingCheckoutIntent</h2>
        <div className="space-y-2">
          {data.billing_intents.length ? data.billing_intents.map((intent) => (
            <div key={intent.id} className="grid gap-3 border border-border-pg bg-bg-panel-muted p-3 text-sm xl:grid-cols-[1.5fr_1fr_1fr_auto]">
              <div>
                <div className="font-medium">{intent.public_reference}</div>
                <div className="mt-1 text-xs text-text-pg-muted">{intent.user_id}</div>
              </div>
              <div>
                <div>{intent.plan_name}</div>
                <div className="mt-1 text-xs text-text-pg-muted">{intent.checkout_mode}</div>
              </div>
              <div className="text-xs text-text-pg-muted">
                <div>{intent.stripe_price_id || "price_id pending"}</div>
                <div className="mt-1">{intent.stripe_checkout_session_id || "session pending"}</div>
              </div>
              <div className="flex flex-wrap items-start gap-2 xl:justify-end">
                <Badge tone="neutral"><StatusDot tone={intent.status === "completed" ? "emerald" : intent.status === "requires_manual_review" ? "amber" : "neutral"} /> {intent.status}</Badge>
                {manualReviewReason(intent) ? <span className="w-full text-xs text-status-warning xl:text-right">{manualReviewReason(intent)}</span> : null}
              </div>
            </div>
          )) : <div className="text-sm text-text-pg-muted">No billing intents in mock state.</div>}
        </div>
      </ResearchCard>
      </div>
    </AdminGate>
  );
}
