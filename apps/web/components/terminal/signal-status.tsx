"use client";

export type SignalTone = "good" | "warn" | "accent" | "idle";

/** Unified, honest status signal. Text always present — never color-only. */
export function SignalStatus({ tone = "idle", label, className = "" }: { tone?: SignalTone; label: string; className?: string }) {
  const cls = tone === "good" ? "signal-chip-good" : tone === "warn" ? "signal-chip-warn" : tone === "accent" ? "signal-chip-accent" : "signal-chip-idle";
  return <span className={"signal-chip " + cls + " " + className}>{label}</span>;
}
