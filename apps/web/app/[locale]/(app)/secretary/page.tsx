import type { Metadata } from "next";
import { SecretaryConsole } from "@/components/secretary-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return { title: locale === "zh" ? "私人秘书 | PureGamma AI" : "Private Secretary | PureGamma AI", description: locale === "zh" ? "基于记忆与工作流的私人研究秘书。" : "A private research secretary grounded in your memory and workflows." };
}
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function SecretaryPage({ params }: { params: { locale: Locale } }) {
  return <SecretaryConsole locale={params.locale} />;
}
