import { notFound } from "next/navigation";
import { AgentFluidQa } from "@/components/ocean/agent-fluid-qa";

export const dynamic = "force-dynamic";

export default function AgentFluidQaPage() {
  if (process.env.ENABLE_QA_SURFACES !== "true") notFound();
  return <AgentFluidQa />;
}
