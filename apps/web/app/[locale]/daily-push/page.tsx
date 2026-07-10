import type { Metadata } from "next";
import { DailyBriefPreview, Badge, CreditCostBadge, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { getBillingSubscription, getDailyPushPreferences } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace, t } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "daily-push", "/daily-push");
}

export default async function DailyPushPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "daily-push");
  const [data, subscription] = await Promise.all([getDailyPushPreferences(locale), getBillingSubscription(locale)]);
  const allowed = subscription.plan === "Max" || subscription.plan === "Enterprise";
  const settings = [
    [t(locale, "common.forms.enabled"), String(data.preference.enabled)],
    [t(locale, "common.forms.localTime"), data.preference.localTime],
    [t(locale, "common.forms.timezone"), data.preference.timezone],
    [t(locale, "common.forms.pushType"), data.preference.pushType],
    [t(locale, "common.forms.channel"), data.preference.channel]
  ];
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        sectionNumber="06"
        actions={<CreditCostBadge locale={locale} cost={3} />}
      />
      {!allowed ? <ResearchCard className="border-border-pg-strong bg-bg-panel-muted"><Badge tone="neutral"><StatusDot tone="amber" /> {copy.entitlement}</Badge></ResearchCard> : null}
      <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <div className="space-y-4">
          <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.deliverySettings}</h2><div className="grid gap-3 md:grid-cols-2">{settings.map(([key, value]) => <label key={key} className="text-sm"><span className="mb-1 block text-text-pg-muted">{key}</span><input className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2" defaultValue={value} /></label>)}</div></ResearchCard>
          <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.contentControls}</h2><div className="grid gap-3 md:grid-cols-2">{copy.controls.map((item) => <label key={item} className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-3 text-sm"><span>{item}</span><input type="checkbox" defaultChecked aria-label={item} /></label>)}</div></ResearchCard>
        </div>
        <DailyBriefPreview locale={locale} />
      </div>
      <ResearchCard><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.modules.sendTest}</h2><Badge tone="neutral"><StatusDot tone={allowed ? "emerald" : "amber"} /> {allowed ? t(locale, "common.badges.entitlementReady") : t(locale, "common.badges.entitlementDenied")}</Badge></div><button className="border border-border-pg px-4 py-2 text-sm hover:border-border-pg-strong">{t(locale, "common.actions.sendTestPush")}</button></ResearchCard>
      <ResearchCard><h2 className="mb-3 font-semibold">{copy.modules.deliveryLedger}</h2><div className="space-y-2">{data.history.map((item) => <div key={item.scheduled_for} className="grid gap-2 border border-border-pg bg-bg-panel-muted p-3 text-sm md:grid-cols-4"><span>{item.scheduled_for}</span><Badge tone="neutral"><StatusDot tone={item.status === "sent" || item.status === "已发送" ? "emerald" : "amber"} /> {item.status}</Badge><span>{item.sent_at || "-"}</span><span className="text-status-warning">{item.failure_reason || "-"}</span></div>)}</div></ResearchCard>
    </div>
  );
}
