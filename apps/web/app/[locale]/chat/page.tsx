import type { Metadata } from "next";
import { AgentChat } from "@/components/agent-chat";
import { ChronoSlices, ChronoSlice } from "@/components/chrono/chrono-slices";
import { isLocale, type Locale } from "@/i18n/routing";
import { IntelligenceShell } from "@/components/terminal/intelligence-shell";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "Agent 对话 | PureGamma AI" : "Agent Chat | PureGamma AI", description: zh ? "与研究 Agent 对话：策略、事件、风险与投资笔记。" : "Chat with your research Agent about strategies, events, risk, and notes." };
}

export default function ChatPage({ params }: { params: { locale: Locale } }) {
  return (
    <ChronoSlices>
      <ChronoSlice>
        <IntelligenceShell eyebrow={params.locale === "zh" ? "Reason" : "Reason"} title={params.locale === "zh" ? "与 Agent 共同推理。" : "Reason with your Agent."} byline={params.locale === "zh" ? "围绕策略、事件与风险的持续推理对象。" : "A continuously updating counterpart for strategies, events and risk."}>
          <AgentChat locale={params.locale} />
        </IntelligenceShell>
      </ChronoSlice>
    </ChronoSlices>
  );
}