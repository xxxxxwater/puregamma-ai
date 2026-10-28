"use client";

import { useEffect, useRef, useState } from "react";
import { ShieldAlert } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import { humanizeToolName } from "@/lib/agent-run-events";

export type PendingToolApproval = {
  toolCallId: string;
  tool: string;
  arguments: Record<string, unknown>;
  expiresAt?: string;
  permissionMode?: string;
};

const COPY = {
  en: {
    title: "Approve this one action?",
    action: "Proposed action",
    scope: "Scope",
    scopeValue: "This conversation only · your own PureGamma account",
    impact: "Impact",
    impactValue: "This tool can change state in your account. The Agent pauses this step until you decide.",
    permission: "Permission used",
    permissionValue: (mode: string) => `Conversation mode “${mode === "read-only" ? "Read only" : "Ask before changes"}” — single-use approval`,
    validity: "Valid for",
    expiresIn: (seconds: number) => `${seconds}s — then it is treated as rejected`,
    expired: "Expired — treated as rejected",
    inputs: "Inputs (redacted)",
    allow: "Allow once",
    deny: "Reject",
  },
  zh: {
    title: "是否批准这一次操作？",
    action: "拟执行动作",
    scope: "范围",
    scopeValue: "仅限本对话 · 你自己的 PureGamma 账户",
    impact: "影响",
    impactValue: "该工具可能修改你账户内的状态。在你决定前，Agent 会暂停这一步。",
    permission: "所用权限",
    permissionValue: (mode: string) => `对话模式「${mode === "read-only" ? "仅可查看" : "修改前确认"}」——单次有效的批准`,
    validity: "有效期",
    expiresIn: (seconds: number) => `${seconds} 秒——超时视为拒绝`,
    expired: "已过期——视为拒绝",
    inputs: "输入（已脱敏）",
    allow: "允许这一次",
    deny: "拒绝",
  },
};

/**
 * A single tool call waiting for the user, stated in full: what, where, what
 * it changes, under which permission, and for how long the approval window is
 * open. The server enforces identity, ownership, expiry and single use; this
 * card only asks.
 */
export function ToolApprovalCard({ approval, locale, busy, onDecide }: { approval: PendingToolApproval; locale: Locale; busy: boolean; onDecide: (decision: "approved" | "denied") => void }) {
  const copy = COPY[locale === "zh" ? "zh" : "en"];
  const [now, setNow] = useState(() => Date.now());
  const cardRef = useRef<HTMLElement | null>(null);
  // The run is paused on this card: bring it into view once, without
  // stealing focus from someone typing in the composer.
  useEffect(() => {
    cardRef.current?.scrollIntoView({ block: "nearest" });
  }, [approval.toolCallId]);
  useEffect(() => {
    if (!approval.expiresAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [approval.expiresAt]);
  const expiresAt = approval.expiresAt ? Date.parse(approval.expiresAt) : NaN;
  const seconds = Number.isNaN(expiresAt) ? null : Math.floor((expiresAt - now) / 1000);
  const expired = seconds !== null && seconds <= 0;
  return (
    <section ref={cardRef} role="alertdialog" aria-labelledby={`approval-${approval.toolCallId}`} className="rounded-lg border border-status-warning bg-[var(--pg-surface-2)] p-3" data-testid="tool-approval">
      <h3 id={`approval-${approval.toolCallId}`} className="flex items-center gap-2 text-sm font-medium"><ShieldAlert className="h-4 w-4 text-status-warning" aria-hidden />{copy.title}</h3>
      <dl className="mt-2 grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
        <dt className="text-text-pg-muted">{copy.action}</dt>
        <dd className="break-words font-medium">{humanizeToolName(approval.tool)}</dd>
        <dt className="text-text-pg-muted">{copy.scope}</dt>
        <dd>{copy.scopeValue}</dd>
        <dt className="text-text-pg-muted">{copy.impact}</dt>
        <dd>{copy.impactValue}</dd>
        <dt className="text-text-pg-muted">{copy.permission}</dt>
        <dd>{copy.permissionValue(approval.permissionMode || "workspace-write")}</dd>
        {seconds !== null ? (<><dt className="text-text-pg-muted">{copy.validity}</dt><dd data-testid="tool-approval-validity" className={expired ? "text-status-negative" : ""}>{expired ? copy.expired : copy.expiresIn(seconds)}</dd></>) : null}
      </dl>
      <details className="mt-2 text-xs"><summary className="cursor-pointer">{copy.inputs}</summary><pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(approval.arguments, null, 2)}</pre></details>
      <div className="mt-3 flex gap-2">
        <button type="button" disabled={busy || expired} onClick={() => onDecide("denied")} className="min-h-10 rounded-md border border-[var(--pg-border-default)] px-4 text-sm disabled:opacity-40">{copy.deny}</button>
        <button type="button" disabled={busy || expired} onClick={() => onDecide("approved")} className="min-h-10 rounded-md border border-status-warning px-4 text-sm font-medium text-status-warning disabled:opacity-40">{copy.allow}</button>
      </div>
    </section>
  );
}
