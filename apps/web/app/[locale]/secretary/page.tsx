import type { Metadata } from "next";
import { SecretaryConsole } from "@/components/secretary-console";
import type { Locale } from "@/i18n/routing";

export const metadata: Metadata = { title: "Private Secretary | PureGamma AI" };
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function SecretaryPage({ params }: { params: { locale: Locale } }) {
  return <SecretaryConsole locale={params.locale} />;
}
