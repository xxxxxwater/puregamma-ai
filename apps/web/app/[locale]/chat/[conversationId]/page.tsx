import type { Metadata } from "next";
import { AgentChat } from "@/components/agent-chat";
import { IntelligenceShell } from "@/components/terminal/intelligence-shell";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string; conversationId: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? `对话 ${params.conversationId} | PureGamma AI` : `Conversation ${params.conversationId} | PureGamma AI`, description: zh ? "与研究 Agent 的历史对话。" : "A past conversation with your research Agent." };
}

export default function ConversationPage({ params }: { params: { locale: Locale; conversationId: string } }) {
  return <IntelligenceShell compact eyebrow="Reason" title={params.locale === "zh" ? "与 Agent 共同推理。" : "Reason with your Agent."} byline={params.locale === "zh" ? "围绕策略、事件与风险的持续推理对象。" : "A continuously updating counterpart for strategies, events and risk."}><AgentChat locale={params.locale} initialConversationId={params.conversationId} /></IntelligenceShell>;
}
