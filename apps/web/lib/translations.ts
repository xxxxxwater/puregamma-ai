import adminEn from "@/messages/en/admin.json";
import billingEn from "@/messages/en/billing.json";
import commonEn from "@/messages/en/common.json";
import complianceEn from "@/messages/en/compliance.json";
import dashboardEn from "@/messages/en/dashboard.json";
import dataSourcesEn from "@/messages/en/data-sources.json";
import dailyPushEn from "@/messages/en/daily-push.json";
import errorsEn from "@/messages/en/errors.json";
import integrationsEn from "@/messages/en/integrations.json";
import landingEn from "@/messages/en/landing.json";
import nautilusEn from "@/messages/en/nautilus.json";
import onboardingEn from "@/messages/en/onboarding.json";
import playbooksEn from "@/messages/en/playbooks.json";
import portfolioEn from "@/messages/en/portfolio.json";
import reportsEn from "@/messages/en/reports.json";
import signalsEn from "@/messages/en/signals.json";
import adminZh from "@/messages/zh/admin.json";
import billingZh from "@/messages/zh/billing.json";
import commonZh from "@/messages/zh/common.json";
import complianceZh from "@/messages/zh/compliance.json";
import dashboardZh from "@/messages/zh/dashboard.json";
import dataSourcesZh from "@/messages/zh/data-sources.json";
import dailyPushZh from "@/messages/zh/daily-push.json";
import errorsZh from "@/messages/zh/errors.json";
import integrationsZh from "@/messages/zh/integrations.json";
import landingZh from "@/messages/zh/landing.json";
import nautilusZh from "@/messages/zh/nautilus.json";
import onboardingZh from "@/messages/zh/onboarding.json";
import playbooksZh from "@/messages/zh/playbooks.json";
import portfolioZh from "@/messages/zh/portfolio.json";
import reportsZh from "@/messages/zh/reports.json";
import signalsZh from "@/messages/zh/signals.json";
import { defaultLocale, normalizeLocale, type Locale } from "@/i18n/routing";

const en = {
  admin: adminEn,
  billing: billingEn,
  common: commonEn,
  compliance: complianceEn,
  dashboard: dashboardEn,
  "data-sources": dataSourcesEn,
  "daily-push": dailyPushEn,
  errors: errorsEn,
  integrations: integrationsEn,
  landing: landingEn,
  nautilus: nautilusEn,
  onboarding: onboardingEn,
  playbooks: playbooksEn,
  portfolio: portfolioEn,
  reports: reportsEn,
  signals: signalsEn
} as const;

const zh = {
  admin: adminZh,
  billing: billingZh,
  common: commonZh,
  compliance: complianceZh,
  dashboard: dashboardZh,
  "data-sources": dataSourcesZh,
  "daily-push": dailyPushZh,
  errors: errorsZh,
  integrations: integrationsZh,
  landing: landingZh,
  nautilus: nautilusZh,
  onboarding: onboardingZh,
  playbooks: playbooksZh,
  portfolio: portfolioZh,
  reports: reportsZh,
  signals: signalsZh
} as const;

export const messages = { en, zh } as const;

export type Messages = typeof en;
type Primitive = string | number | boolean | null;
type DotPrefix<T extends string, U extends string> = `${T}.${U}`;
type DotNestedKeys<T> = T extends Primitive | readonly unknown[]
  ? never
  : {
      [K in keyof T & string]: T[K] extends string ? K : T[K] extends Primitive | readonly unknown[] ? never : DotPrefix<K, DotNestedKeys<T[K]>>;
    }[keyof T & string];

export type TranslationKey = DotNestedKeys<Messages>;
type InterpolationValues = Record<string, string | number>;

export function getMessages(locale: Locale): Messages {
  return messages[normalizeLocale(locale)];
}

export function getMessageNamespace<K extends keyof Messages>(locale: Locale, namespace: K): Messages[K] {
  return getMessages(locale)[namespace];
}

export function t(locale: Locale, key: TranslationKey, values?: InterpolationValues): string {
  const value = readKey(getMessages(locale), key) ?? readKey(getMessages(defaultLocale), key);
  if (typeof value !== "string") {
    return interpolate(readKey(getMessages(locale), "errors.missingTranslation") || key, { key });
  }
  return interpolate(value, values);
}

export function hasTranslation(locale: Locale, key: TranslationKey): boolean {
  return typeof readKey(getMessages(locale), key) === "string";
}

function readKey(source: unknown, key: string): string | undefined {
  const value = key.split(".").reduce<unknown>((current, part) => {
    if (current && typeof current === "object" && part in current) {
      return (current as Record<string, unknown>)[part];
    }
    return undefined;
  }, source);
  return typeof value === "string" ? value : undefined;
}

function interpolate(template: string, values?: InterpolationValues): string {
  if (!values) return template;
  return Object.entries(values).reduce((copy, [key, value]) => copy.replaceAll(`{${key}}`, String(value)), template);
}
