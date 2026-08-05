import type { Metadata } from "next";
import { AgentChat } from "@/components/agent-chat";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  const zh = locale === "zh";
  return { title: zh ? "Agent 对话 | PureGamma AI" : "Agent Chat | PureGamma AI", description: zh ? "与研究 Agent 对话：策略、事件、风险与投资笔记。" : "Chat with your research Agent about strategies, events, risk, and notes." };
}

export default function ChatPage({ params }: { params: { locale: Locale } }) {
  return <AgentChat locale={params.locale} />;
}
