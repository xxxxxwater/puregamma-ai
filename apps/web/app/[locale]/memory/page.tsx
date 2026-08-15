import type { Metadata } from "next";
import { MemoryConsole } from "@/components/memory-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "记忆 | PureGamma AI" : "Memory | PureGamma AI", description: zh ? "Agent 记忆与授权：scope 开关、记忆提议、删除与导出。" : "Agent memory and consent: scope switches, proposals, deletion, and export." };
}

export default function MemoryPage({ params }: { params: { locale: Locale } }) {
  return <MemoryConsole locale={params.locale} />;
}