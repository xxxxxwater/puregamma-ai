import type { NavSnapshot, TradingSafetyStatus } from "@/lib/api";

/**
 * LIVE trading UI state machine.
 *
 * The console derives ONE state from the server's `/api/trading/safety-status`
 * response — never from scattered booleans assembled client-side. States:
 *
 * - UNAVAILABLE      endpoint 404/501/network failure → no trading UI at all
 * - LIVE_DISABLED    static gate failed → honest explanation only
 * - PENDING_APPROVAL static gate passed, user not yet LIVE-approved
 * - KILLED           a kill switch is engaged → everything blocked
 * - PAUSED           a LIVE mandate is paused
 * - READY            all gates passed → full console
 *
 * Pure functions only: no React, no fetch. Kept side-effect free so the
 * gating logic can be tested in isolation.
 */

export type LiveUiState =
  | "UNAVAILABLE"
  | "LIVE_DISABLED"
  | "PENDING_APPROVAL"
  | "KILLED"
  | "PAUSED"
  | "READY";

export function deriveLiveUiState(
  safety: TradingSafetyStatus | null | undefined,
  unavailable: boolean
): LiveUiState {
  if (unavailable || !safety || !safety.static_gate) return "UNAVAILABLE";
  if (!safety.static_gate.enabled) return "LIVE_DISABLED";
  if ((safety.kill_switches || []).length > 0) return "KILLED";
  if ((safety.user_live_approval || {}).status !== "approved") return "PENDING_APPROVAL";
  const mandateGates = Object.values(safety.mandates || {});
  if (mandateGates.some((gate) => isPausedMandateGate(gate))) return "PAUSED";
  return "READY";
}

type MandateGate = { enabled?: boolean; state?: string; checks?: Record<string, { ok?: boolean; detail?: unknown }> };

function isPausedMandateGate(gate: MandateGate): boolean {
  const check = gate.checks?.["mandate_approved"];
  if (!check || check.ok) return false;
  return /paused\s*=\s*true/i.test(String(check.detail ?? ""));
}

/**
 * Formats an API Decimal string for display WITHOUT any float math: the
 * string is grouped and trimmed as text, so "1234567.89012345" renders as
 * "1,234,567.89012345" with zero binary-float risk. Returns "" for empty.
 */
export function formatDecimalString(
  value: string | null | undefined,
  maximumFractionDigits = 8
): string {
  if (value == null || value === "") return "";
  let sign = "";
  let rest = value.trim();
  if (rest.startsWith("-")) {
    sign = "-";
    rest = rest.slice(1);
  } else if (rest.startsWith("+")) {
    rest = rest.slice(1);
  }
  const [intPart, fractionPart] = rest.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (fractionPart === undefined) return `${sign}${grouped}`;
  const trimmed = fractionPart.slice(0, maximumFractionDigits);
  return trimmed ? `${sign}${grouped}.${trimmed}` : `${sign}${grouped}`;
}

export type NavResolution =
  | { kind: "value"; value: string }
  | { kind: "stale" }
  | { kind: "missing" };

/**
 * Server NAV display rule (NULL semantics): a stale snapshot or a missing
 * price must render as "—" — the UI never shows an old number as current.
 * The backend computes `is_stale` and NULLs `nav` itself; this is the
 * client-side mirror of that rule and never invents a value.
 */
export function resolveNav(nav: NavSnapshot | null | undefined): NavResolution {
  if (!nav) return { kind: "missing" };
  if (nav.nav == null || nav.is_stale) return { kind: "stale" };
  return { kind: "value", value: nav.nav };
}

/**
 * True when a client_order_id belongs to an order that may still be canceled.
 * The API returns LiveOrderStatus values lowercase ("accepted", "submitted",
 * "partially_filled", "pending", "unknown") — normalize before comparing.
 */
export function isOpenLiveOrderStatus(status: string | null | undefined): boolean {
  const normalized = (status || "").toLowerCase();
  return (
    normalized === "pending" ||
    normalized === "submitted" ||
    normalized === "accepted" ||
    normalized === "partially_filled" ||
    normalized === "unknown"
  );
}

/**
 * Exact product of two non-negative decimal strings, as a decimal string.
 *
 * Used for the "about this much notional" line of a LIMIT order approval
 * (quantity × limit price). BigInt keeps it exact: a binary float would
 * already be wrong in the cents for a large quantity. Returns null for
 * anything that is not a plain decimal.
 */
export function multiplyDecimalStrings(a: string | null | undefined, b: string | null | undefined): string | null {
  const pattern = /^\d+(\.\d+)?$/;
  if (!a || !b || !pattern.test(a.trim()) || !pattern.test(b.trim())) return null;
  const split = (value: string) => {
    const [whole, fraction = ""] = value.trim().split(".");
    return { digits: BigInt(`${whole}${fraction}` || "0"), scale: fraction.length };
  };
  const left = split(a);
  const right = split(b);
  const scale = left.scale + right.scale;
  const raw = (left.digits * right.digits).toString().padStart(scale + 1, "0");
  if (scale === 0) return raw;
  const whole = raw.slice(0, raw.length - scale).replace(/^0+(?=\d)/, "");
  const fraction = raw.slice(raw.length - scale).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

/**
 * What a failed LIVE confirm means for the money.
 *
 * - "rejected": the control plane answered (a 4xx): the order was not placed,
 *   for the stated reason (expired, token mismatch, gate closed, risk check).
 * - "ambiguous": no answer, a timeout, or a 5xx. The server may already hold
 *   the order. The console must reconcile against the order list and may only
 *   re-send the SAME intent (server-side idempotent per intent), never preview
 *   and submit a new one.
 */
export type SubmitFailureKind = "rejected" | "ambiguous";

export function classifySubmitFailure(error: unknown): SubmitFailureKind {
  const status = (error as { status?: number } | null)?.status;
  if (typeof status !== "number" || status === 0) return "ambiguous";
  if (status === 408 || status === 425 || status >= 500) return "ambiguous";
  return "rejected";
}

/** Whole seconds until an ISO timestamp (negative once passed); null if unparseable. */
export function secondsUntil(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  return Number.isNaN(at) ? null : Math.floor((at - now) / 1000);
}

const SECRET_KEY = /(secret|token|password|passphrase|api[_-]?key|signature|authorization|cookie|credential|private)/i;

/**
 * A connection health payload reduced to flat, display-safe rows.
 * Credential-like keys are masked even though the server should never send
 * them: this is the last place a mistake there could reach a screen.
 */
export function displayHealthRows(health: Record<string, unknown> | null | undefined): Array<{ key: string; value: string }> {
  if (!health || typeof health !== "object") return [];
  return Object.entries(health).slice(0, 24).map(([key, value]) => {
    if (SECRET_KEY.test(key)) return { key, value: "••••" };
    if (value == null) return { key, value: "—" };
    if (typeof value === "object") return { key, value: Array.isArray(value) ? `${value.length} items` : "{…}" };
    const text = String(value);
    return { key, value: text.length > 120 ? `${text.slice(0, 120)}…` : text };
  });
}

/** True when an order's outcome at the venue is not known and must not be retried. */
export function isUnknownLiveOrderStatus(status: string | null | undefined): boolean {
  return (status || "").toLowerCase() === "unknown";
}
