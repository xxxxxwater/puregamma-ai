/**
 * Projection of one Agent run's server events into what the transcript shows.
 *
 * Pure functions over the events `/api/agent/conversations/{id}/messages`
 * streams and `/api/agent/runs/{id}/events` replays. Nothing here is stored:
 * the server's durable event log and persisted messages stay the only state,
 * and a reload rebuilds this view from them. This is the legacy Agent client's
 * view layer until the DeepSeek Harness Session path owns the transcript.
 */

export type ToolStepStatus = "awaiting_approval" | "running" | "completed" | "failed" | "denied";

export type ToolStep = {
  id: string;
  tool: string;
  status: ToolStepStatus;
  /** Server time the step started (`at` of approval.required / tool.started). */
  startedAt?: string;
  completedAt?: string;
  latencyMs?: number;
  /** Already redacted by the server; shown as-is. */
  arguments?: Record<string, unknown>;
  summary?: string;
  error?: string;
};

/**
 * True when a frame must be ignored because this client already applied it.
 * Every frame carries a monotonic per-run `seq`; a replayed or re-delivered
 * frame at or below the cursor is a duplicate, never new information.
 */
export function isAlreadyApplied(data: Record<string, unknown>, lastSeq: number): boolean {
  return typeof data.seq === "number" && data.seq <= lastSeq;
}

/** True when a frame names a different run than the one being shown. */
export function isForeignRun(data: Record<string, unknown>, activeRunId: string): boolean {
  return Boolean(activeRunId) && typeof data.runId === "string" && data.runId !== activeRunId;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

const DENIAL = /READ_ONLY_PERMISSION|APPROVAL_DENIED|DENIED/;

export function applyToolEvent(steps: ToolStep[], event: string, data: Record<string, unknown>): ToolStep[] {
  if (event !== "approval.required" && event !== "tool.started" && event !== "tool.completed") return steps;
  const tool = text(data.tool) || "tool";
  const id = text(data.toolCallId) || `${tool}-${typeof data.seq === "number" ? data.seq : steps.length}`;
  const at = text(data.at);
  const index = steps.findIndex((step) => step.id === id);
  const current: ToolStep = index >= 0 ? steps[index] : { id, tool, status: "running" };
  let next: ToolStep;
  if (event === "approval.required") {
    next = { ...current, tool, status: "awaiting_approval", startedAt: current.startedAt || at, arguments: record(data.arguments) ?? current.arguments };
  } else if (event === "tool.started") {
    next = { ...current, tool, status: "running", startedAt: current.startedAt || at, arguments: record(data.arguments) ?? current.arguments };
  } else {
    const error = text(data.error);
    next = {
      ...current,
      tool,
      status: error ? (DENIAL.test(error) ? "denied" : "failed") : "completed",
      completedAt: at,
      latencyMs: typeof data.latencyMs === "number" ? data.latencyMs : current.latencyMs,
      summary: text(data.summary) ?? current.summary,
      error,
    };
  }
  if (index < 0) return [...steps, next];
  const copy = [...steps];
  copy[index] = next;
  return copy;
}

/** Duration of a finished step in ms, from server times when available. */
export function stepDurationMs(step: ToolStep): number | null {
  if (typeof step.latencyMs === "number") return step.latencyMs;
  if (!step.startedAt || !step.completedAt) return null;
  const start = Date.parse(step.startedAt);
  const end = Date.parse(step.completedAt);
  return Number.isNaN(start) || Number.isNaN(end) || end < start ? null : end - start;
}

export function humanizeToolName(tool: string): string {
  const words = tool.replace(/[_-]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : tool;
}

/**
 * Turn `[n]` citation markers into in-page links for sources that exist.
 * Fenced code is left alone; a marker already followed by `(` (a markdown
 * link) is not touched.
 */
export function linkCitations(content: string, messageId: string, indices: ReadonlySet<number>): string {
  if (!indices.size || !content.includes("[")) return content;
  return content
    .split(/(```[\s\S]*?```)/g)
    .map((part, index) =>
      index % 2 === 1
        ? part
        : part.replace(/\[(\d{1,3})\](?!\()/g, (match, digits: string) => (indices.has(Number(digits)) ? `[[${digits}]](#cite-${messageId}-${digits})` : match)),
    )
    .join("");
}

/** Age of a source in whole minutes, or null when its time is unknown. */
export function sourceAgeMinutes(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  return Number.isNaN(at) ? null : Math.max(0, Math.floor((now - at) / 60000));
}

/** A fresh id for one send attempt; reused only when that same attempt is retried. */
export function newClientRequestId(): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `web-${random}`;
}
