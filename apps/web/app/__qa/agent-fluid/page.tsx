import { notFound } from "next/navigation";
import { AgentFluidQa } from "@/components/ocean/agent-fluid-qa";

export const dynamic = "force-dynamic";

export default function AgentFluidQaPage() {
  // Local development and CI need a deterministic harness without carrying a
  // public runtime flag. Production remains closed unless explicitly enabled.
  if (process.env.NODE_ENV === "production" && process.env.ENABLE_QA_SURFACES !== "true") notFound();
  return <AgentFluidQa />;
}
