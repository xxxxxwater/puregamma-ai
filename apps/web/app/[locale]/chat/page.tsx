import { AgentChat } from "@/components/agent-chat";
import type { Locale } from "@/i18n/routing";

export default function ChatPage({ params }: { params: { locale: Locale } }) {
  return <AgentChat locale={params.locale} />;
}
