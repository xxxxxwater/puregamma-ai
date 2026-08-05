import type { Metadata } from "next";
import { AgentChat } from "@/components/agent-chat";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string; conversationId: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? `对话 ${params.conversationId} | PureGamma AI` : `Conversation ${params.conversationId} | PureGamma AI`, description: zh ? "与研究 Agent 的历史对话。" : "A past conversation with your research Agent." };
}

export default function ConversationPage({ params }: { params: { locale: Locale; conversationId: string } }) {
  return <AgentChat locale={params.locale} initialConversationId={params.conversationId} />;
}
