import type { Metadata } from "next";
import { type Locale } from "@/i18n/routing";
import { getMessages, type Messages } from "@/lib/translations";

const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://puregamma.ai";

type SeoNamespace = {
  seo: {
    title: string;
    description: string;
  };
};

type SeoKey = {
  [K in keyof Messages]: Messages[K] extends SeoNamespace ? K : never;
}[keyof Messages];

export function localizedMetadata(locale: Locale, namespace: SeoKey, path = ""): Metadata {
  const messages = getMessages(locale);
  const page = messages[namespace] as SeoNamespace;
  const suffix = path ? `/${path.replace(/^\/+/, "")}` : "";
  const canonical = `${baseUrl}/${locale}${suffix}`;
  return {
    title: page.seo.title,
    description: page.seo.description,
    alternates: {
      canonical,
      languages: {
        en: `${baseUrl}/en${suffix}`,
        zh: `${baseUrl}/zh${suffix}`
      }
    },
    openGraph: {
      title: page.seo.title,
      description: page.seo.description,
      locale: locale === "zh" ? "zh_CN" : "en_US",
      alternateLocale: locale === "zh" ? ["en_US"] : ["zh_CN"],
      url: canonical,
      siteName: "PureGamma.ai"
    }
  };
}
