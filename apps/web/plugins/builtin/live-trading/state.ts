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
