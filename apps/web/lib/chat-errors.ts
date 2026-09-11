import type { Locale } from "@/i18n/routing";
import { getMessageNamespace } from "@/lib/translations";

/**
 * User-facing Agent Chat error text.
 *
 * The Agent stream can fail in four very different ways and the raw text is not
 * suitable for a general user: `requestStrict` throws the raw response body,
 * which for a proxy or gateway failure can contain an upstream address or a
 * provider stack trace. This module maps a failure onto a short, actionable
 * sentence and keeps only a *redacted* request reference.
 */

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{6,80}$/;

/** Response headers the API uses to publish a safe, shareable request id. */
const REQUEST_ID_HEADERS = ["x-request-id", "x-correlation-id", "request-id"];

export type ChatErrorKind =
  | "empty_answer"
  | "stream_interrupted"
  | "rate_limited"
  | "service_unavailable"
  | "network"
  | "generic";

export type ChatFailure = {
  kind: ChatErrorKind;
  /** Short, localized, user-safe sentence. */
  message: string;
  /** Redacted request id worth quoting in a support ticket, when supplied. */
  reference?: string;
  /**
   * Billing status for THIS run, taken only from the backend's settlement
   * record. `undefined` means the backend did not report one, and the UI must
   * not imply either outcome.
   *
   * `apps/api/services/agent_service.py` settles a run in three different ways,
   * and they are not interchangeable:
   *   - an error inside `stream_run` refunds (`run.failed` after
   *     `_refund_agent_run`);
   *   - a client disconnect *settles* the tokens already produced
   *     (`_finalize_disconnected_run`);
   *   - stale-run recovery refunds after a 10-minute grace period
   *     (`recover_stale_runs`).
   * So "the stream broke" never justifies a refund promise on its own.
   */
  billing?: "refunded" | "settled" | "unknown";
};

/**
 * Keep a server-supplied request id only when it looks like an opaque id.
 *
 * Anything with whitespace, quotes, a URL scheme or a path separator is
 * dropped rather than echoed to the browser: an id that carries a hostname or a
 * file path would leak internal topology, which is exactly what this function
 * exists to prevent.
 */
export function safeRequestReference(value: string | null | undefined): string | undefined {
  const candidate = (value || "").trim();
  if (!candidate) return undefined;
  if (!REQUEST_ID_PATTERN.test(candidate)) return undefined;
  if (candidate.includes("//") || candidate.includes("..")) return undefined;
  return candidate;
}

export function requestReferenceFromHeaders(headers: Headers | undefined): string | undefined {
  if (!headers) return undefined;
  for (const name of REQUEST_ID_HEADERS) {
    const found = safeRequestReference(headers.get(name));
    if (found) return found;
  }
  return undefined;
}

/**
 * Extract a safe id from an error thrown by `lib/api.ts`.
 *
 * The thrown `Error.message` holds the raw response body, so it is parsed for
 * an explicit `request_id` / `error_id` / `trace_id` field only. The rest of the
 * body is deliberately discarded instead of displayed.
 */
function referenceFromError(error: unknown): string | undefined {
  const provided = safeRequestReference((error as { requestId?: string } | null)?.requestId);
  if (provided) return provided;
  const message = (error as { message?: string } | null)?.message || "";
  if (!message.startsWith("{") && !message.startsWith("[")) return undefined;
  try {
    const parsed = JSON.parse(message) as { detail?: unknown; request_id?: unknown; error_id?: unknown; trace_id?: unknown };
    const detail = (parsed && typeof parsed.detail === "object" ? parsed.detail : {}) as Record<string, unknown>;
    for (const candidate of [parsed?.request_id, parsed?.error_id, parsed?.trace_id, detail.request_id, detail.error_id, detail.trace_id]) {
      const found = safeRequestReference(typeof candidate === "string" ? candidate : undefined);
      if (found) return found;
    }
    const code = safeRequestReference(typeof detail.code === "string" ? detail.code : undefined);
    return code;
  } catch {
    return undefined;
  }
}

/** Machine-readable codes the API returns for failures worth their own copy. */
const CODE_KINDS: Record<string, ChatErrorKind> = {
  AGENT_MODEL_TIMEOUT: "service_unavailable",
  AGENT_MODEL_UNAVAILABLE: "service_unavailable",
  AGENT_RUN_FAILED: "generic",
  MODEL_NOT_CONFIGURED: "service_unavailable",
  API_UNAVAILABLE: "service_unavailable",
  NETWORK_ERROR: "network",
  RATE_LIMITED: "rate_limited",
  QUOTA_EXCEEDED: "rate_limited",
  CONCURRENT_RUN_LIMIT: "rate_limited",
  AGENT_LIMIT: "rate_limited",
  SKILL_RUNTIME_TIMEOUT: "service_unavailable",
};

function genericCodeFromMessage(message: string): string | undefined {
  if (!message.startsWith("{")) return undefined;
  try {
    const parsed = JSON.parse(message) as { detail?: { code?: string } | string; code?: string };
    if (typeof parsed.code === "string") return parsed.code;
    if (parsed.detail && typeof parsed.detail === "object" && typeof parsed.detail.code === "string") return parsed.detail.code;
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return undefined;
  }
  return undefined;
}

/**
 * Turn any Agent failure into localized, user-safe copy plus an optional
 * redacted reference. Never returns raw server text, addresses or stack traces.
 *
 * `override.refunded` is the backend's settlement result for the run
 * (`AgentMessage.credits_refunded`). Pass it whenever it is known so the billing
 * line states a fact instead of a guess; leave it undefined when it is not.
 */
export function describeChatFailure(
  locale: Locale,
  error: unknown,
  override?: { kind: ChatErrorKind; status?: number; reference?: string; refunded?: boolean; settled?: boolean },
): ChatFailure {
  const copy = getMessageNamespace(locale, "model-upgrade").errors;
  const status = override?.status ?? (error as { status?: number } | null)?.status;
  const rawMessage = (error as { message?: string } | null)?.message || "";
  const code = genericCodeFromMessage(rawMessage);
  const reference = override?.reference ?? referenceFromError(error);

  let kind: ChatErrorKind;
  if (override?.kind) {
    kind = override.kind;
  } else if (code && CODE_KINDS[code]) {
    kind = CODE_KINDS[code];
  } else if (status === 429) {
    kind = "rate_limited";
  } else if (status === 503 || status === 502 || status === 504) {
    kind = "service_unavailable";
  } else if (status === 0) {
    kind = "network";
  } else if (status === undefined && /failed to fetch|networkerror|load failed|network request failed/i.test(rawMessage)) {
    kind = "network";
  } else {
    kind = "generic";
  }

  const messages: Record<ChatErrorKind, string> = {
    empty_answer: copy.emptyAnswer,
    stream_interrupted: copy.streamInterrupted,
    rate_limited: copy.rateLimited,
    service_unavailable: copy.serviceUnavailable,
    network: copy.network,
    generic: copy.generic,
  };

  // Only a reported settlement result may be stated. A refund is only ever
  // asserted when the backend says so; otherwise stay neutral and point at the
  // usage record, which is the surface that actually knows.
  const billing: ChatFailure["billing"] =
    override?.refunded === true ? "refunded" : override?.settled === true ? "settled" : "unknown";
  const billingMessage =
    billing === "refunded" ? copy.billingRefunded : billing === "settled" ? copy.billingSettled : copy.billingUnknown;

  return { kind, message: messages[kind], reference, billing };
}

/** Localized billing sentence for a reported settlement state. */
export function billingNotice(locale: Locale, billing: ChatFailure["billing"]): string {
  const copy = getMessageNamespace(locale, "model-upgrade").errors;
  if (billing === "refunded") return copy.billingRefunded;
  if (billing === "settled") return copy.billingSettled;
  return copy.billingUnknown;
}
