import type { Metadata } from "next";
import { DailyPushSettings } from "@/components/daily-push-settings";
import { PageHeader } from "@/components/puregamma";
import { getBillingSubscription, getDailyPushPreferences } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "daily-push", "/daily-push");
}

export default async function DailyPushPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "daily-push");
  // Keep this page aligned with the single-channel preference schema exposed by the API.
  // The preference read is strict: when it fails the page says so instead of
  // crashing, and it does not offer a form pre-filled with defaults - saving
  // that would overwrite the user's real schedule with values they never chose.
  const [preferences, subscription] = await Promise.all([
    getDailyPushPreferences(locale).catch(() => null),
    getBillingSubscription(locale),
  ]);
  const zh = locale === "zh";
  return <div className="space-y-5"><PageHeader eyebrow={copy.eyebrow} title={copy.title} description={copy.subtitle} sectionNumber="06" />{preferences ? <DailyPushSettings initial={preferences.preference} initialHistory={preferences.history} locale={locale} plan={subscription.plan} /> : <section role="status" data-testid="daily-push-unavailable" className="rounded-xl border border-border-pg bg-bg-panel p-5"><h2 className="font-semibold">{zh ? "暂时无法读取推送设置" : "Delivery settings are unavailable right now"}</h2><p className="mt-2 text-sm leading-6 text-text-pg-muted">{zh ? "服务没有返回你的每日推送设置。为避免用默认值覆盖你的真实设置，此处暂不显示编辑表单。请稍后刷新。" : "The service did not return your daily delivery settings. To avoid overwriting your real schedule with defaults, the editor is hidden until they load. Refresh in a moment."}</p></section>}</div>;
}
