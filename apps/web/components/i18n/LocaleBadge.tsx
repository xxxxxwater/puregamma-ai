import { Badge } from "@/components/puregamma";
import type { Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export function LocaleBadge({ locale }: { locale: Locale }) {
  return <Badge tone="neutral">{t(locale, "common.localeName")}</Badge>;
}
