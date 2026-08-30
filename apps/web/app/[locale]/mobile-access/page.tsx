import type { Metadata } from "next";
import { IMessageSection } from "@/components/imessage-section";
import { MobileAccessPanel } from "@/components/mobile-access-panel";
import { PageHeader } from "@/components/puregamma";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "mobile-access", "/mobile-access");
}

export default async function MobileAccessPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const copy = getMessageNamespace(locale, "mobile-access");
  return (
    <div className="space-y-5">
      <PageHeader eyebrow={copy.eyebrow} title={copy.title} description={copy.subtitle} sectionNumber="01" />
      <MobileAccessPanel copy={copy.remote} />
      <IMessageSection copy={copy.imessage} />
    </div>
  );
}
