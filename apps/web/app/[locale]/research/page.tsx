import type { Metadata } from "next";
import { ResearchConsole } from "@/components/research-console";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "研究 | PureGamma AI" : "Research | PureGamma AI", description: zh ? "智能研究工作台：深度研究任务、证据与限制条件。" : "Intelligence research workbench: deep research runs, evidence, and limitations." };
}

export default function ResearchPage({ params }: { params: { locale: Locale } }) {
  return <ResearchConsole locale={params.locale} />;
}
