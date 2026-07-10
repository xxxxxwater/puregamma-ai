import { AgentChat } from "@/components/agent-chat";
import type { Locale } from "@/i18n/routing";

export default function ConversationPage({ params }: { params: { locale: Locale; conversationId: string } }) {
  return <AgentChat locale={params.locale} initialConversationId={params.conversationId} />;
}
