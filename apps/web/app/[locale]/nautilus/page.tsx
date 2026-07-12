import type { Metadata } from "next";
import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import { localizedMetadata } from "@/lib/metadata";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata { const locale = isLocale(params.locale) ? params.locale : "en"; return localizedMetadata(locale, "nautilus", "/nautilus"); }
export default function NautilusPage({ params }: { params: { locale: Locale } }) { return <StrategyRuntimeConsole locale={params.locale} />; }
