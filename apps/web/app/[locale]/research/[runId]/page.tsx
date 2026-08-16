import type { Metadata } from "next";
import { ResearchRunDetail } from "@/components/research-run-detail";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string; runId: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? `研究任务 ${params.runId} | PureGamma AI` : `Research run ${params.runId} | PureGamma AI`, description: zh ? "研究任务详情：时间线、证据关系与研究产出。" : "Research run detail: timeline, evidence relationships, and artifact." };
}

export default function ResearchRunPage({ params }: { params: { locale: Locale; runId: string } }) {
  return <ResearchRunDetail locale={params.locale} runId={params.runId} />;
}
