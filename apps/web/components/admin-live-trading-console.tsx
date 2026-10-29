"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, RefreshCw, ShieldAlert } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import {
  describeApiError,
  getAdminKillSwitches,
  getAdminLiveApprovals,
  getAdminReconciliations,
  getAdminTradingAudit,
  reviewAdminReconciliation,
  setAdminKillSwitch,
  setAdminLiveApproval,
  type AdminKillSwitch,
  type AdminLiveApproval,
  type AdminReconciliation,
  type AdminTradingAuditEvent,
} from "@/lib/api";
import { useDialogFocus } from "@/lib/use-dialog-focus";
import { formatDecimalString } from "@/plugins/builtin/live-trading/state";

/**
 * LIVE control-plane review for administrators: kill switches, user LIVE
 * eligibility and reconciliation exceptions.
 *
 * Authorization is the server's: every call below is refused with 403 for a
 * non-administrator whatever this page renders. Every change asks for a
 * reason, shows exactly what will happen, and needs a typed confirmation; the
 * server records the administrator and reason in the trading audit log.
 */

type Load<T> = { kind: "loading" } | { kind: "failed"; message: string } | { kind: "ready"; data: T };

function useLoad<T>(read: () => Promise<T>) {
  const [load, setLoad] = useState<Load<T>>({ kind: "loading" });
  const reload = useCallback(async () => {
    setLoad({ kind: "loading" });
    try {
      setLoad({ kind: "ready", data: await read() });
    } catch (error) {
      const { status, message } = describeApiError(error);
      setLoad({ kind: "failed", message: status === 403 ? "403" : message });
    }
  }, [read]);
  useEffect(() => { void reload(); }, [reload]);
  return [load, reload] as const;
}

const time = (value: string | null | undefined, locale: Locale) => (value ? new Date(value).toLocaleString(locale) : "—");
const inputClass = "mt-1 w-full rounded-lg border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg";
const buttonClass = "inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-border-pg px-3 text-sm hover:border-border-pg-strong disabled:opacity-40";

export function AdminLiveTradingConsole({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [auditKey, setAuditKey] = useState(0);
  const changed = useCallback(() => setAuditKey((value) => value + 1), []);
  return (
    <div className="space-y-5">
      <p className="rounded-xl border border-border-pg bg-bg-panel p-4 text-sm leading-6 text-text-pg-muted">
        {zh
          ? "这里的操作都由服务器按管理员角色授权，并写入交易审计日志（管理员、原因、时间）。Kill Switch 只阻止新的敞口，查询、撤单、成交记录和对账照常进行；释放 Kill Switch 不会恢复任何 Mandate。本页不能开启实盘。"
          : "Every action here is authorized by the server's admin role check and written to the trading audit log (administrator, reason, time). A kill switch blocks new exposure only; queries, cancels, fill recording and reconciliation keep working, and releasing one resumes no mandate. Nothing on this page can turn LIVE trading on."}
      </p>
      <KillSwitchSection locale={locale} onChanged={changed} />
      <ApprovalSection locale={locale} onChanged={changed} />
      <ReconciliationReviewSection locale={locale} onChanged={changed} />
      <AuditSection key={auditKey} locale={locale} />
    </div>
  );
}

function Section({ title, testId, children, actions }: { title: string; testId: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-xl border border-border-pg bg-bg-panel" data-testid={testId}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-pg p-4">
        <h2 className="font-semibold">{title}</h2>
        {actions}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function LoadState<T>({ load, locale, onRetry, children }: { load: Load<T>; locale: Locale; onRetry: () => void; children: (data: T) => ReactNode }) {
  const zh = locale === "zh";
  if (load.kind === "loading") return <p className="text-sm text-text-pg-muted">{zh ? "加载中…" : "Loading…"}</p>;
  if (load.kind === "failed") {
    return (
      <div role="status" className="flex flex-wrap items-center gap-3 text-sm text-text-pg-muted" data-testid="admin-live-unavailable">
        <span>{load.message === "403" ? (zh ? "服务器拒绝：需要管理员权限。" : "Refused by the server: administrator role required.") : (zh ? "暂时无法读取（不是“没有记录”）。" : "Could not be read right now (this is not “nothing to show”).")}</span>
        <button type="button" onClick={onRetry} className={buttonClass}>{zh ? "重试" : "Retry"}</button>
      </div>
    );
  }
  return <>{children(load.data)}</>;
}

function RefreshButton({ locale, onClick }: { locale: Locale; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={buttonClass}><RefreshCw className="h-3.5 w-3.5" aria-hidden />{locale === "zh" ? "刷新" : "Refresh"}</button>;
}

/**
 * A second, typed confirmation: the action is stated in full and the confirm
 * button stays disabled until the exact phrase is typed.
 */
function ConfirmDialog({ locale, title, summary, phrase, busy, error, onCancel, onConfirm, danger }: { locale: Locale; title: string; summary: ReactNode; phrase: string; busy: boolean; error: string; onCancel: () => void; onConfirm: () => void; danger?: boolean }) {
  const zh = locale === "zh";
  const [typed, setTyped] = useState("");
  const panelRef = useRef<HTMLDivElement | null>(null);
  const backRef = useRef<HTMLButtonElement | null>(null);
  useDialogFocus(true, panelRef, onCancel, backRef);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="admin-live-confirm-title" className={`w-full max-w-md rounded-xl border bg-bg-panel p-5 ${danger ? "border-status-negative" : "border-status-warning"}`}>
        <h3 id="admin-live-confirm-title" className="font-semibold text-status-warning">{title}</h3>
        <div className="mt-3 text-sm leading-6 text-text-pg-muted">{summary}</div>
        <label className="mt-4 block text-xs text-text-pg-muted">
          {zh ? "输入以下文字以确认" : "Type the following to confirm"}
          <code className="mt-1 block break-all rounded-lg bg-bg-panel-muted p-2 text-xs text-text-pg">{phrase}</code>
          <input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" spellCheck={false} className={`${inputClass} font-mono`} />
        </label>
        {error ? <p role="alert" className="mt-2 text-sm text-status-negative">{error}</p> : null}
        <div className="mt-4 flex gap-2">
          <button ref={backRef} type="button" onClick={onCancel} className={`${buttonClass} flex-1`}>{zh ? "返回" : "Back"}</button>
          <button type="button" onClick={onConfirm} disabled={busy || typed.trim() !== phrase} className={`${buttonClass} flex-1 border-status-warning font-semibold text-status-warning`}>{zh ? "确认" : "Confirm"}</button>
        </div>
      </div>
    </div>
  );
}

// ── Kill switches ─────────────────────────────────────────────────────────

type KillAction = { active: boolean; scope: string; scopeId: string | null; reason: string };

function KillSwitchSection({ locale, onChanged }: { locale: Locale; onChanged: () => void }) {
  const zh = locale === "zh";
  const read = useCallback(() => getAdminKillSwitches(), []);
  const [load, reload] = useLoad(read);
  const [scope, setScope] = useState("global");
  const [scopeId, setScopeId] = useState("");
  const [reason, setReason] = useState("");
  const [releaseReason, setReleaseReason] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<KillAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const run = async () => {
    if (!pending) return;
    setBusy(true);
    setError("");
    try {
      await setAdminKillSwitch({ scope: pending.scope, scope_id: pending.scopeId, active: pending.active, reason: pending.reason });
      setNotice(pending.active ? (zh ? "Kill Switch 已启用。" : "Kill switch engaged.") : (zh ? "Kill Switch 已释放；相关 Mandate 仍保持暂停。" : "Kill switch released; affected mandates stay paused."));
      setPending(null);
      setReason("");
      setScopeId("");
      onChanged();
      await reload();
    } catch (cause) {
      setError(describeApiError(cause).message || (zh ? "服务器拒绝了该操作。" : "The server refused this action."));
    } finally {
      setBusy(false);
    }
  };

  const target = (row: { scope: string; scope_id: string | null }) => (row.scope === "global" ? (zh ? "全局" : "global") : `${row.scope} ${row.scope_id}`);
  const engageReady = reason.trim().length > 0 && (scope === "global" || scopeId.trim().length > 0);

  return (
    <Section title={zh ? "Kill Switch" : "Kill switches"} testId="admin-kill-switches" actions={<RefreshButton locale={locale} onClick={() => void reload()} />}>
      {notice ? <p role="status" className="mb-3 text-sm text-status-positive">{notice}</p> : null}
      <LoadState load={load} locale={locale} onRetry={() => void reload()}>
        {(data) => (
          <div className="space-y-4">
            {data.active.length === 0 ? (
              <p className="text-sm text-text-pg-muted" data-testid="admin-kill-none">{zh ? "当前没有启用的 Kill Switch。" : "No kill switch is engaged."}</p>
            ) : (
              <ul className="space-y-2">
                {data.active.map((row: AdminKillSwitch) => (
                  <li key={row.id} className="rounded-lg border border-status-negative p-3 text-sm" data-testid="admin-kill-active">
                    <p className="flex flex-wrap items-center gap-2 font-semibold text-status-negative"><ShieldAlert className="h-4 w-4" aria-hidden />{target(row)}</p>
                    <p className="mt-1 text-xs text-text-pg-muted">{row.reason} · {row.triggered_by} · {time(row.triggered_at, locale)}</p>
                    <div className="mt-2 flex flex-wrap items-end gap-2">
                      <label className="min-w-0 flex-1 text-xs text-text-pg-muted">
                        {zh ? "释放原因（必填）" : "Release reason (required)"}
                        <input value={releaseReason[row.id] || ""} onChange={(event) => setReleaseReason((current) => ({ ...current, [row.id]: event.target.value }))} className={inputClass} />
                      </label>
                      <button type="button" disabled={!(releaseReason[row.id] || "").trim()} onClick={() => { setError(""); setPending({ active: false, scope: row.scope, scopeId: row.scope_id, reason: (releaseReason[row.id] || "").trim() }); }} className={buttonClass}>{zh ? "释放…" : "Release…"}</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="rounded-lg border border-border-pg p-3">
              <h3 className="text-sm font-semibold">{zh ? "启用 Kill Switch" : "Engage a kill switch"}</h3>
              <div className="mt-2 grid gap-3 sm:grid-cols-3">
                <label className="text-xs text-text-pg-muted">
                  {zh ? "范围" : "Scope"}
                  <select value={scope} onChange={(event) => setScope(event.target.value)} className={inputClass}>
                    <option value="global">global</option>
                    <option value="user">user</option>
                    <option value="mandate">mandate</option>
                    <option value="connection">connection</option>
                  </select>
                </label>
                {scope !== "global" ? (
                  <label className="text-xs text-text-pg-muted">
                    {zh ? "对象 ID" : "Target id"}
                    <input value={scopeId} onChange={(event) => setScopeId(event.target.value)} spellCheck={false} className={`${inputClass} font-mono`} />
                  </label>
                ) : null}
                <label className="text-xs text-text-pg-muted sm:col-span-3">
                  {zh ? "原因（必填，写入审计）" : "Reason (required, audited)"}
                  <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} className={inputClass} />
                </label>
              </div>
              <button type="button" disabled={!engageReady} onClick={() => { setError(""); setPending({ active: true, scope, scopeId: scope === "global" ? null : scopeId.trim(), reason: reason.trim() }); }} className={`${buttonClass} mt-3 border-status-negative text-status-negative`}>{zh ? "启用…" : "Engage…"}</button>
            </div>
            {data.released.length ? (
              <details className="text-xs text-text-pg-muted">
                <summary className="cursor-pointer select-none py-1">{zh ? `已释放（${data.released.length}）` : `Released (${data.released.length})`}</summary>
                <ul className="mt-2 space-y-1">
                  {data.released.map((row) => <li key={row.id}>{target(row)} · {row.reason} · {zh ? "释放于" : "released"} {time(row.resolved_at, locale)}</li>)}
                </ul>
              </details>
            ) : null}
          </div>
        )}
      </LoadState>
      {pending ? (
        <ConfirmDialog
          locale={locale}
          danger={pending.active}
          title={pending.active ? (zh ? "启用 Kill Switch" : "Engage kill switch") : (zh ? "释放 Kill Switch" : "Release kill switch")}
          summary={
            <>
              <p className="font-mono text-text-pg">{target({ scope: pending.scope, scope_id: pending.scopeId })}</p>
              <p className="mt-1">{zh ? "原因：" : "Reason: "}{pending.reason}</p>
              <p className="mt-2">{pending.active ? (zh ? "范围内的新订单会被立即拒绝；撤单、查询、成交记录和对账不受影响。" : "New orders in this scope are refused immediately; cancels, queries, fill recording and reconciliation are unaffected.") : (zh ? "释放后新订单仍需通过全部门禁；被暂停的 Mandate 不会自动恢复。" : "After release new orders still pass every gate; paused mandates are not resumed.")}</p>
            </>
          }
          phrase={`${pending.active ? "ENGAGE" : "RELEASE"} ${pending.scope}`}
          busy={busy}
          error={error}
          onCancel={() => setPending(null)}
          onConfirm={() => void run()}
        />
      ) : null}
    </Section>
  );
}

// ── LIVE eligibility ──────────────────────────────────────────────────────

function ApprovalSection({ locale, onChanged }: { locale: Locale; onChanged: () => void }) {
  const zh = locale === "zh";
  const read = useCallback(() => getAdminLiveApprovals(), []);
  const [load, reload] = useLoad(read);
  const [userId, setUserId] = useState("");
  const [approve, setApprove] = useState(true);
  const [cap, setCap] = useState("");
  const [notes, setNotes] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const capValid = /^\d+(\.\d+)?$/.test(cap.trim());
  const ready = userId.trim().length > 0 && notes.trim().length > 0 && capValid;

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const { approval } = await setAdminLiveApproval({ user_id: userId.trim(), approve, max_total_notional: cap.trim(), notes: notes.trim() });
      setNotice(zh ? `已记录：${approval.email || approval.user_id} → ${approval.status}` : `Recorded: ${approval.email || approval.user_id} → ${approval.status}`);
      setConfirming(false);
      setNotes("");
      onChanged();
      await reload();
    } catch (cause) {
      setError(describeApiError(cause).message || (zh ? "服务器拒绝了该操作。" : "The server refused this action."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title={zh ? "用户实盘资格审批" : "User LIVE eligibility"} testId="admin-live-approvals" actions={<RefreshButton locale={locale} onClick={() => void reload()} />}>
      <p className="mb-3 text-xs text-text-pg-muted">{zh ? "批准资格不会开启实盘：部署级开关在每笔订单上独立检查。管理员不能批准自己。" : "Approving eligibility does not turn LIVE on: deployment gates are checked on every order. An administrator cannot approve themselves."}</p>
      {notice ? <p role="status" className="mb-3 text-sm text-status-positive">{notice}</p> : null}
      <LoadState load={load} locale={locale} onRetry={() => void reload()}>
        {(data) => data.approvals.length === 0 ? (
          <p className="text-sm text-text-pg-muted" data-testid="admin-approvals-empty">{zh ? "还没有任何资格审批记录。" : "No eligibility decisions recorded yet."}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-pg-muted">
                <tr className="border-b border-border-pg">{[zh ? "用户" : "User", zh ? "状态" : "Status", zh ? "名义上限" : "Notional cap", zh ? "审批时间" : "Reviewed", zh ? "原因" : "Reason"].map((head) => <th key={head} scope="col" className="p-2 font-medium">{head}</th>)}</tr>
              </thead>
              <tbody>
                {data.approvals.map((row: AdminLiveApproval) => (
                  <tr key={row.id} className="border-b border-border-pg last:border-0" data-testid="admin-approval-row">
                    <td className="p-2 text-xs">{row.email || row.user_id}</td>
                    <td className="p-2 text-xs">{row.status}</td>
                    <td className="p-2 font-mono text-xs tabular-nums">{row.max_total_notional == null ? "—" : formatDecimalString(row.max_total_notional, 2)}</td>
                    <td className="p-2 text-xs text-text-pg-muted">{time(row.reviewed_at, locale)}</td>
                    <td className="max-w-[16rem] truncate p-2 text-xs text-text-pg-muted">{row.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </LoadState>
      <div className="mt-4 grid gap-3 rounded-lg border border-border-pg p-3 sm:grid-cols-2">
        <label className="text-xs text-text-pg-muted">{zh ? "用户 ID" : "User id"}<input value={userId} onChange={(event) => setUserId(event.target.value)} spellCheck={false} className={`${inputClass} font-mono`} /></label>
        <label className="text-xs text-text-pg-muted">
          {zh ? "决定" : "Decision"}
          <select value={approve ? "approve" : "reject"} onChange={(event) => setApprove(event.target.value === "approve")} className={inputClass}>
            <option value="approve">{zh ? "批准" : "Approve"}</option>
            <option value="reject">{zh ? "拒绝/撤销" : "Reject / revoke"}</option>
          </select>
        </label>
        <label className="text-xs text-text-pg-muted">{zh ? "名义上限（十进制）" : "Notional cap (decimal)"}<input value={cap} onChange={(event) => setCap(event.target.value)} inputMode="decimal" className={`${inputClass} font-mono`} /></label>
        <label className="text-xs text-text-pg-muted">{zh ? "原因（必填，写入审计）" : "Reason (required, audited)"}<input value={notes} onChange={(event) => setNotes(event.target.value)} className={inputClass} /></label>
        <div className="sm:col-span-2"><button type="button" disabled={!ready} onClick={() => { setError(""); setConfirming(true); }} className={buttonClass}>{zh ? "提交…" : "Submit…"}</button></div>
      </div>
      {confirming ? (
        <ConfirmDialog
          locale={locale}
          title={approve ? (zh ? "批准实盘资格" : "Approve LIVE eligibility") : (zh ? "拒绝/撤销实盘资格" : "Reject / revoke LIVE eligibility")}
          summary={<><p className="font-mono text-text-pg">{userId.trim()}</p><p className="mt-1">{zh ? "名义上限：" : "Notional cap: "}<span className="font-mono">{cap.trim()}</span></p><p className="mt-1">{zh ? "原因：" : "Reason: "}{notes.trim()}</p></>}
          phrase={`${approve ? "APPROVE" : "REJECT"} ${userId.trim()}`}
          busy={busy}
          error={error}
          onCancel={() => setConfirming(false)}
          onConfirm={() => void run()}
        />
      ) : null}
    </Section>
  );
}

// ── Reconciliation exceptions ─────────────────────────────────────────────

function ReconciliationReviewSection({ locale, onChanged }: { locale: Locale; onChanged: () => void }) {
  const zh = locale === "zh";
  const [unreviewedOnly, setUnreviewedOnly] = useState(true);
  const read = useCallback(() => getAdminReconciliations({ unreviewedOnly }), [unreviewedOnly]);
  const [load, reload] = useLoad(read);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [target, setTarget] = useState<AdminReconciliation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!target) return;
    setBusy(true);
    setError("");
    try {
      await reviewAdminReconciliation(target.id, (notes[target.id] || "").trim());
      setTarget(null);
      onChanged();
      await reload();
    } catch (cause) {
      setError(describeApiError(cause).message || (zh ? "服务器拒绝了该操作。" : "The server refused this action."));
    } finally {
      setBusy(false);
    }
  };

  const amount = (value: unknown) => (value == null ? "—" : formatDecimalString(String(value)));
  return (
    <Section
      title={zh ? "对账异常" : "Reconciliation exceptions"}
      testId="admin-reconciliations"
      actions={
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-text-pg-muted"><input type="checkbox" checked={unreviewedOnly} onChange={(event) => setUnreviewedOnly(event.target.checked)} />{zh ? "只看未审阅" : "Unreviewed only"}</label>
          <RefreshButton locale={locale} onClick={() => void reload()} />
        </div>
      }
    >
      <p className="mb-3 text-xs text-text-pg-muted">{zh ? "差异只读显示。标记已审阅只追加一条审计记录，不改写对账、不修改 Ledger、不恢复被暂停的 Mandate。" : "Differences are read-only. Marking reviewed appends an audit row; it does not rewrite the reconciliation, touch the ledger, or resume the paused mandate."}</p>
      <LoadState load={load} locale={locale} onRetry={() => void reload()}>
        {(data) => data.reconciliations.length === 0 ? (
          <p className="text-sm text-text-pg-muted" data-testid="admin-recon-empty">{unreviewedOnly ? (zh ? "没有待审阅的对账异常。" : "No unreviewed reconciliation exceptions.") : (zh ? "没有对账异常记录。" : "No reconciliation exceptions recorded.")}</p>
        ) : (
          <ul className="space-y-3">
            {data.reconciliations.map((row: AdminReconciliation) => (
              <li key={row.id} className="rounded-lg border border-status-warning p-3 text-sm" data-testid="admin-recon-row">
                <p className="flex flex-wrap items-center gap-2"><AlertTriangle className="h-4 w-4 text-status-warning" aria-hidden /><span className="font-semibold">{row.status}</span><span className="text-xs text-text-pg-muted">{time(row.created_at, locale)} · {zh ? "用户" : "user"} <span className="font-mono">{row.user_id}</span> · {zh ? "账户" : "account"} <span className="font-mono">{row.account_id}</span></span></p>
                <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                  <div><dt className="text-text-pg-muted">{zh ? "交易所现金" : "Exchange cash"}</dt><dd className="font-mono">{amount(row.exchange_balance.cash)}</dd></div>
                  <div><dt className="text-text-pg-muted">{zh ? "Ledger 现金" : "Ledger cash"}</dt><dd className="font-mono">{amount(row.ledger_balance.cash)}</dd></div>
                  <div><dt className="text-text-pg-muted">{zh ? "NAV 现金" : "NAV cash"}</dt><dd className="font-mono">{amount(row.nav.cash)}</dd></div>
                </dl>
                <ul className="mt-2 space-y-1 text-xs" data-testid="admin-recon-differences">
                  {row.differences.map((difference, index) => (
                    <li key={index} className="font-mono">{String(difference.source ?? "—")}{difference.delta != null ? ` Δ ${amount(difference.delta)}` : ""}{difference.detail ? ` · ${difference.detail}` : ""}</li>
                  ))}
                </ul>
                {row.actions.length ? <p className="mt-1 text-xs text-text-pg-dim">{zh ? "已执行：" : "Actions taken: "}{row.actions.join(", ")}</p> : null}
                {row.reviewed ? (
                  <p className="mt-2 text-xs text-status-positive" data-testid="admin-recon-reviewed">{zh ? "已审阅" : "Reviewed"} · {time(row.reviewed.reviewed_at, locale)} · {row.reviewed.note}</p>
                ) : (
                  <div className="mt-2 flex flex-wrap items-end gap-2">
                    <label className="min-w-0 flex-1 text-xs text-text-pg-muted">{zh ? "审阅备注（必填）" : "Review note (required)"}<input value={notes[row.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))} className={inputClass} /></label>
                    <button type="button" disabled={!(notes[row.id] || "").trim()} onClick={() => { setError(""); setTarget(row); }} className={buttonClass}>{zh ? "标记已审阅…" : "Mark reviewed…"}</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </LoadState>
      {target ? (
        <ConfirmDialog
          locale={locale}
          title={zh ? "标记对账已审阅" : "Mark reconciliation reviewed"}
          summary={<><p className="font-mono text-text-pg">{target.id}</p><p className="mt-1">{zh ? "备注：" : "Note: "}{(notes[target.id] || "").trim()}</p></>}
          phrase={`REVIEWED ${target.id.slice(0, 8)}`}
          busy={busy}
          error={error}
          onCancel={() => setTarget(null)}
          onConfirm={() => void run()}
        />
      ) : null}
    </Section>
  );
}

// ── Audit trail ───────────────────────────────────────────────────────────

function AuditSection({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const read = useCallback(() => getAdminTradingAudit(), []);
  const [load, reload] = useLoad(read);
  return (
    <Section title={zh ? "管理操作审计" : "Administrator audit trail"} testId="admin-live-audit" actions={<RefreshButton locale={locale} onClick={() => void reload()} />}>
      <LoadState load={load} locale={locale} onRetry={() => void reload()}>
        {(data) => data.events.length === 0 ? (
          <p className="text-sm text-text-pg-muted">{zh ? "还没有管理操作记录。" : "No administrator actions recorded yet."}</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {data.events.map((event: AdminTradingAuditEvent) => (
              <li key={event.id} className="flex flex-wrap gap-x-2" data-testid="admin-audit-row">
                <span className="text-text-pg-muted">{time(event.created_at, locale)}</span>
                <span className="font-mono">{event.action}</span>
                <span className="font-mono text-text-pg-dim">{event.admin_user_id || "—"}</span>
                <span className="min-w-0 break-words text-text-pg-muted">{String(event.request.reason ?? event.request.note ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
      </LoadState>
    </Section>
  );
}
