import type { Metadata } from "next";
import { ResearchConsole } from "@/components/research-console";
import { ChronoSlices, ChronoSlice } from "@/components/chrono/chrono-slices";
import { isLocale, type Locale } from "@/i18n/routing";
import { IntelligenceShell } from "@/components/terminal/intelligence-shell";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "研究 | PureGamma AI" : "Research | PureGamma AI", description: zh ? "智能研究工作台：深度研究任务、证据与限制条件。" : "Intelligence research workbench: deep research runs, evidence, and limitations." };
}

export default function ResearchPage({ params }: { params: { locale: Locale } }) {
  return (
    <ChronoSlices>
      <ChronoSlice>
        <IntelligenceShell eyebrow={params.locale === "zh" ? "Research" : "Research"} title={params.locale === "zh" ? "研究正在执行。" : "Research is running."} byline={params.locale === "zh" ? "深度任务、证据与边界——由 Agent 执行。" : "Deep tasks, evidence and limits — executed by the Agent."}>
          <ResearchConsole locale={params.locale} />
        </IntelligenceShell>
      </ChronoSlice>
    </ChronoSlices>
  );
}