"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, RefreshCw, Search, ShieldAlert, WalletCards } from "lucide-react";
import { Badge, ResearchCard, StatusDot } from "@/components/puregamma";
import { Button } from "@/components/ui";
import {
  type AdminCreditAccount,
  type AdminCreditAccountDetail,
  getAdminCreditAccount,
  getAdminCreditAccounts,
  grantAdminCredits,
  refundAdminCreditLedgerEntry,
  refundAdminCreditReservation,
} from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const inputClass = "min-h-10 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg outline-none transition focus:border-border-pg-strong";

function messageFromError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  try {
    const parsed = JSON.parse(error.message) as { detail?: string };
    return parsed.detail || fallback;
  } catch {
    return error.message || fallback;
  }
}

function formatTime(value: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function AdminCreditConsole({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [accounts, setAccounts] = useState<AdminCreditAccount[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminCreditAccountDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [credits, setCredits] = useState("100");
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const grantKey = useRef("");

  const loadAccounts = useCallback(async (search = "") => {
    setLoading(true);
    setError("");
    try {
      const data = await getAdminCreditAccounts(search);
      setAccounts(data.accounts);
      setTotal(data.total);
      if (!selectedId && data.accounts.length) setSelectedId(data.accounts[0].id);
    } catch (requestError) {
      setError(messageFromError(requestError, zh ? "无法读取账户数据。" : "Unable to load account data."));
    } finally {
      setLoading(false);
    }
  }, [selectedId, zh]);

  const loadDetail = useCallback(async (userId: string) => {
    setDetailLoading(true);
    setError("");
    try {
      setDetail(await getAdminCreditAccount(userId));
    } catch (requestError) {
      setDetail(null);
      setError(messageFromError(requestError, zh ? "无法读取 Credits 账本。" : "Unable to load the Credit ledger."));
    } finally {
      setDetailLoading(false);
    }
  }, [zh]);

  useEffect(() => { void loadAccounts(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selectedId) void loadDetail(selectedId); }, [loadDetail, selectedId]);

  async function submitGrant(event: FormEvent) {
    event.preventDefault();
    if (!selectedId) return;
    const amount = Number(credits);
    if (!Number.isInteger(amount) || amount < 1 || amount > 5000) {
      setError(zh ? "单次增加必须为 1–5000 的整数。" : "Grant must be an integer from 1 to 5,000.");
      return;
    }
    if (!grantKey.current) grantKey.current = `admin-console-${selectedId}-${crypto.randomUUID()}`;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const result = await grantAdminCredits(selectedId, {
        credits: amount,
        reason,
        reference,
        idempotency_key: grantKey.current,
      });
      setSuccess(zh ? `已增加 ${result.grant.credits} Credits，余额 ${result.credit_balance}。` : `Granted ${result.grant.credits} Credits. Balance: ${result.credit_balance}.`);
      grantKey.current = "";
      setReason("");
      setReference("");
      await Promise.all([loadDetail(selectedId), loadAccounts(query)]);
    } catch (requestError) {
      setError(messageFromError(requestError, zh ? "增加 Credits 失败。" : "Credit grant failed."));
    } finally {
      setBusy(false);
    }
  }

  async function executeRefund(kind: "reservation" | "ledger", id: string, amount: number) {
    if (!reference.trim() || !reason.trim()) {
      setError(zh ? "退款前请填写原因和工单/外部参考号。" : "Enter a reason and ticket/reference before refunding.");
      return;
    }
    const confirmed = window.confirm(zh ? `确认退回最多 ${amount} Credits？该操作会写入审计账本。` : `Refund up to ${amount} Credits? This will be written to the audit ledger.`);
    if (!confirmed || !selectedId) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const payload = { reason, reference };
      const result = kind === "reservation"
        ? await refundAdminCreditReservation(id, payload)
        : await refundAdminCreditLedgerEntry(id, payload);
      setSuccess(zh ? `退款已完成，当前余额 ${result.credit_balance}。` : `Refund completed. Current balance: ${result.credit_balance}.`);
      await Promise.all([loadDetail(selectedId), loadAccounts(query)]);
    } catch (requestError) {
      setError(messageFromError(requestError, zh ? "退款失败。" : "Refund failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <ResearchCard className="h-fit">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">{zh ? "账户" : "Accounts"}</h2>
              <p className="text-xs text-text-pg-muted">{total} {zh ? "个数据库账户" : "database accounts"}</p>
            </div>
            <Button variant="secondary" disabled={loading} onClick={() => void loadAccounts(query)} aria-label={zh ? "刷新" : "Refresh"}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
          <form className="mb-3 flex gap-2" onSubmit={(event) => { event.preventDefault(); void loadAccounts(query); }}>
            <input className={inputClass} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "邮箱、姓名或用户 ID" : "Email, name, or user ID"} />
            <Button type="submit" variant="secondary"><Search className="h-4 w-4" /></Button>
          </form>
          <div className="max-h-[680px] space-y-2 overflow-y-auto pr-1">
            {accounts.map((account) => (
              <button
                key={account.id}
                type="button"
                onClick={() => setSelectedId(account.id)}
                className={`w-full border p-3 text-left transition  rounded-lg ${selectedId === account.id ? "border-border-pg-strong bg-bg-panel-muted" : "border-border-pg hover:border-border-pg-strong"}`}
              >
                <div className="truncate text-sm font-medium">{account.email}</div>
                <div className="mt-2 flex items-center justify-between gap-2 text-xs text-text-pg-muted">
                  <span>{account.plan}</span>
                  <span className="font-mono text-text-pg">{account.credit_balance} Credits</span>
                </div>
              </button>
            ))}
            {!loading && !accounts.length ? <p className="py-8 text-center text-sm text-text-pg-muted">{zh ? "没有匹配账户" : "No matching accounts"}</p> : null}
          </div>
        </ResearchCard>

        <div className="min-w-0 space-y-4">
          {error ? <div className="flex gap-2 border border-status-negative/40 bg-bg-panel p-3 text-sm text-status-negative rounded-lg"><ShieldAlert className="h-4 w-4 shrink-0" />{error}</div> : null}
          {success ? <div className="flex gap-2 border border-status-positive/40 bg-bg-panel p-3 text-sm text-status-positive rounded-lg"><CheckCircle2 className="h-4 w-4 shrink-0" />{success}</div> : null}
          {detailLoading ? <ResearchCard><p className="text-sm text-text-pg-muted">{zh ? "正在读取数据库账本…" : "Loading database ledger…"}</p></ResearchCard> : null}
          {detail && !detailLoading ? (
            <>
              <ResearchCard>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-semibold">{detail.account.email}</h2><Badge>{detail.account.role}</Badge><Badge tone="neutral">{detail.account.plan}</Badge></div>
                    <p className="mt-1 font-mono text-xs text-text-pg-muted">{detail.account.id}</p>
                  </div>
                  <div className="text-right"><div className="text-3xl font-semibold">{detail.account.credit_balance}</div><div className="text-xs text-text-pg-muted">Credits</div></div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  <Badge tone={detail.reconciliation.matches ? "emerald" : "red"}><StatusDot tone={detail.reconciliation.matches ? "emerald" : "red"} /> {detail.reconciliation.matches ? (zh ? "账本已对平" : "Ledger reconciled") : (zh ? "账本不一致" : "Ledger mismatch")}</Badge>
                  <Badge tone="neutral">{detail.reconciliation.ledger_entries} {zh ? "条账本记录" : "ledger entries"}</Badge>
                  <Badge tone="neutral">{detail.account.auth_provider}</Badge>
                </div>
              </ResearchCard>

              <ResearchCard>
                <div className="mb-4 flex items-center gap-2"><WalletCards className="h-4 w-4" /><h2 className="font-semibold">{zh ? "增加 Credits / 退款资料" : "Grant Credits / Refund Details"}</h2></div>
                <form className="grid gap-3 lg:grid-cols-[140px_1fr_1fr_auto]" onSubmit={submitGrant}>
                  <label className="text-xs text-text-pg-muted">{zh ? "增加数量" : "Grant amount"}<input className={`${inputClass} mt-1`} type="number" min={1} max={5000} step={1} value={credits} onChange={(event) => { setCredits(event.target.value); grantKey.current = ""; }} required /></label>
                  <label className="text-xs text-text-pg-muted">{zh ? "原因" : "Reason"}<input className={`${inputClass} mt-1`} value={reason} onChange={(event) => { setReason(event.target.value); grantKey.current = ""; }} minLength={3} maxLength={300} placeholder={zh ? "例如：客服补偿" : "e.g. support adjustment"} required /></label>
                  <label className="text-xs text-text-pg-muted">{zh ? "工单/外部参考号" : "Ticket / reference"}<input className={`${inputClass} mt-1`} value={reference} onChange={(event) => { setReference(event.target.value); grantKey.current = ""; }} minLength={3} maxLength={120} placeholder="PG-1001" required /></label>
                  <Button className="self-end" type="submit" disabled={busy}>{zh ? "增加 Credits" : "Grant Credits"}</Button>
                </form>
                <p className="mt-2 text-xs text-text-pg-dim">{zh ? "原因和参考号同时用于下方退款；所有操作由服务器写入不可修改的 Credits 账本。" : "Reason and reference also apply to refunds below. Every operation is written server-side to the append-only Credit ledger."}</p>
              </ResearchCard>

              <ResearchCard>
                <h2 className="mb-3 font-semibold">{zh ? "预扣与结算" : "Reservations & settlements"}</h2>
                <div className="space-y-2">
                  {detail.reservations.map((row) => (
                    <div key={row.id} className="grid gap-3 border border-border-pg bg-bg-panel-muted p-3 text-sm md:grid-cols-[1fr_auto_auto] md:items-center rounded-lg">
                      <div><div className="font-medium">{row.task_type}</div><div className="mt-1 font-mono text-xs text-text-pg-muted">{row.id} · {formatTime(row.created_at, locale)}</div></div>
                      <div className="flex items-center gap-2"><Badge tone="neutral">{row.status}</Badge><span>{row.settled_credits ?? row.reserved_credits}/{row.reserved_credits}</span></div>
                      <Button variant="secondary" disabled={busy || !row.refundable} onClick={() => void executeRefund("reservation", row.id, row.reserved_credits)}>{row.refundable ? (zh ? "退回预扣" : "Refund reservation") : (zh ? "不可退款" : "Terminal")}</Button>
                    </div>
                  ))}
                  {!detail.reservations.length ? <p className="text-sm text-text-pg-muted">{zh ? "暂无预扣记录。" : "No reservations."}</p> : null}
                </div>
              </ResearchCard>

              <ResearchCard>
                <h2 className="mb-3 font-semibold">{zh ? "Credits 账本" : "Credit ledger"}</h2>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="border-b border-border-pg text-xs text-text-pg-muted"><tr><th className="p-2">{zh ? "时间" : "Time"}</th><th className="p-2">{zh ? "动作" : "Action"}</th><th className="p-2">{zh ? "变动" : "Delta"}</th><th className="p-2">{zh ? "余额" : "Balance"}</th><th className="p-2">{zh ? "参考" : "Reference"}</th><th className="p-2 text-right">{zh ? "操作" : "Action"}</th></tr></thead>
                    <tbody>{detail.ledger.map((row) => (
                      <tr key={row.id} className="border-b border-border-pg/70">
                        <td className="p-2 text-xs text-text-pg-muted">{formatTime(row.created_at, locale)}</td>
                        <td className="p-2">{row.action}</td>
                        <td className={`p-2 font-mono ${row.credits_delta >= 0 ? "text-status-positive" : "text-status-negative"}`}>{row.credits_delta > 0 ? "+" : ""}{row.credits_delta}</td>
                        <td className="p-2 font-mono">{row.balance_after}</td>
                        <td className="max-w-[180px] truncate p-2 text-xs text-text-pg-muted">{String(row.metadata.reference || row.metadata.reason || "—")}</td>
                        <td className="p-2 text-right"><Button variant="secondary" disabled={busy || !row.refundable} onClick={() => void executeRefund("ledger", row.id, Math.abs(row.credits_delta))}>{row.refundable ? (zh ? "退回" : "Refund") : (zh ? "—" : "—")}</Button></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </ResearchCard>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
