import type { Metadata } from "next";
import { NewsFeed } from "@/components/news-feed";
import { PageHeader } from "@/components/puregamma";
import { getNewsFeed } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "news", "/news");
}

export default async function NewsPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "news");
  const initial = await getNewsFeed(locale, { kind: "flash", source: "chaincatcher", language: locale, hours: 72, limit: 30 });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow={copy.eyebrow} title={copy.title} description={copy.subtitle} sectionNumber="01" />
      <NewsFeed locale={locale} initial={initial} copy={copy} />
    </div>
  );
}
