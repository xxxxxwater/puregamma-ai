"use client";

import { useState } from "react";
import { Ban, CirclePause, PlayCircle, ShieldCheck, ShieldX } from "lucide-react";
import { StatusBadge } from "@/components/ocean/status-badge";
import { pauseTradingMandate, resumeTradingMandate, type TradingMandate, type TradingSafetyStatus } from "@/lib/api";

function envBadgeValue(environment: string): string {
  const upper = (environment || "").toUpperCase();
  if (upper === "PAPER") return "PAPER";
  if (upper === "SHADOW") return "SHADOW";
  if (upper === "LIVE" || upper === "PRODUCTION") return "LIVE";
  return "LIVE_DISABLED";
}

function money(value: string | null | undefined, locale: string): string {
  const parsed = Number(value);
  if (value == null || Number.isNaN(parsed)) return "--";
  return `$${parsed.toLocaleString(locale, { maximumFractionDigits: 2 })}`;
}

/**
 * Trading Safety card for Trading Safety / Portfolio surfaces.
 * Calm, static, auditable. Emphasizes: environment, LIVE disabled state,
 * mandate/risk limits, last review time, pause/resume permission.
 * No glowing buttons, no animation, no LIVE order affordances.
 */
export function TradingSafetyCard({ safety, mandates, locale, onRetry }: {
  safety: TradingSafetyStatus | null;
  mandates: TradingMandate[];
  locale: "en" | "zh";
  onRetry: () => void;
}) {
  const zh = locale === "zh";
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState<{ id: string; mode: "pause" | "resume" } | null>(null);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const liveDisabled = !safety?.static_gate.enabled;
  const gateState = safety?.static_gate.state || "LIVE_DISABLED";
  const envBadge = liveDisabled ? "LIVE_DISABLED" : "LIVE";
  const approval = safety?.user_live_approval;
  const activeKillSwitches = (safety?.kill_switches || []).length;

  const pause = async (mandate: TradingMandate) => {
    if (!reason.trim()) return;
    setBusy(`pause:${mandate.id}`);
    setError("");
    try {
      await pauseTradingMandate(mandate.id, reason.trim());
      setConfirming(null);
      setReason("");
      onRetry();
    } catch (cause) {
      setError(formatError(cause, zh));
    } finally {
      setBusy("");
    }
  };

  const resume = async (mandate: TradingMandate) => {
    if (confirmation.trim().length < 8) return;
    setBusy(`resume:${mandate.id}`);
    setError("");
    try {
      await resumeTradingMandate(mandate.id, confirmation.trim());
      setConfirming(null);
      setConfirmation("");
      onRetry();
    } catch (cause) {
      setError(formatError(cause, zh));
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="border border-border-pg bg-bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-pg p-4">
        <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4" aria-hidden />{zh ? "交易安全状态" : "Trading safety status"}</h2>
        <div className="flex items-center gap-2">
          <StatusBadge domain="trading" value={envBadge} locale={locale} />
          {!safety ? <span className="text-xs text-text-pg-dim">{zh ? "状态不可用" : "unavailable"}</span> : null}
        </div>
      </div>

      <div className="space-y-4 p-4">
        {liveDisabled ? (
          <div className="flex items-start gap-3 border border-status-warning bg-bg-panel-muted p-3" role="status">
            {safety ? <ShieldX className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden /> : <Ban className="mt-0.5 h-5 w-5 shrink-0 text-text-pg-muted" aria-hidden />}
            <div>
              <p className="text-sm font-semibold text-status-warning">{zh ? "实盘交易当前未启用" : "LIVE trading is disabled"}</p>
              <p className="mt-1 text-xs leading-5 text-text-pg-muted">
                {safety
                  ? zh ? "该页面不提供任何可执行的 LIVE 交易入口；即使后端标记启用，前端策略仍保持禁用 LIVE 操作。" : "This page provides no executable LIVE trading entry; even if the backend flag is enabled, the frontend policy keeps LIVE actions disabled."
                  : zh ? "安全状态暂不可用，按未启用处理；不提供任何可执行的 LIVE 交易入口。" : "Safety status is unavailable and treated as disabled; no executable LIVE trading entry is provided."}
              </p>
              {safety ? (
                <dl className="mt-3 grid gap-x-6 gap-y-1.5 border-t border-border-pg pt-3 text-xs text-text-pg-muted sm:grid-cols-2">
                  {Object.entries(safety.static_gate.checks).map(([name, check]) => (
                    <div key={name} className="flex items-center justify-between gap-3">
                      <dt className="min-w-0 truncate">{name}</dt>
                      <dd className={`shrink-0 ${check.ok ? "text-status-positive" : "text-status-warning"}`}>{check.ok ? (zh ? "通过" : "ok") : (zh ? "未通过" : "blocked")}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              <p className="mt-2 text-[10px] text-text-pg-dim">{zh ? "环境状态" : "Gate state"}: {gateState}</p>
            </div>
          </div>
        ) : null}

        {approval ? (
          <dl className="grid gap-px border border-border-pg bg-border-pg sm:grid-cols-3">
            <Field label={zh ? "实盘审批" : "LIVE approval"} value={String(approval.status)} />
            <Field label={zh ? "审批名义上限" : "Approved max notional"} value={money(approval.max_total_notional, locale)} />
            <Field label={zh ? "最后审查时间" : "Last reviewed"} value={approval.reviewed_at ? new Date(approval.reviewed_at).toLocaleString(locale) : (zh ? "从未审查" : "never reviewed")} />
          </dl>
        ) : null}

        {activeKillSwitches > 0 ? (
          <p className="border border-status-negative p-3 text-sm text-status-negative" role="alert">
            {zh ? `存在 ${activeKillSwitches} 个已激活的熔断开关。所有交易活动已被阻断。` : `${activeKillSwitches} kill switch(es) active. All trading activity is blocked.`}
          </p>
        ) : null}

        {mandates.length === 0 ? (
          <p className="text-sm text-text-pg-muted">{zh ? "暂无交易 Mandate。Mandate 创建后，单笔上限、总敞口、杠杆与日亏损限制会显示在这里。" : "No trading mandates yet. Once a mandate exists, per-order limits, total exposure, leverage, and daily loss limits appear here."}</p>
        ) : (
          <div className="space-y-4">
            {mandates.map((mandate) => (
              <div key={mandate.id} className="border border-border-pg">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-pg bg-bg-panel-muted px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-medium text-text-pg">{zh ? "Mandate" : "Mandate"} {mandate.id.slice(0, 8)}</span>
                    <StatusBadge domain="trading" value={envBadgeValue(mandate.environment)} locale={locale} />
                    <span className={`text-[10px] uppercase ${mandate.paused ? "text-status-warning" : "text-status-positive"}`}>{mandate.paused ? (zh ? "已暂停" : "paused") : (zh ? "运行中" : "active")}</span>
                    {mandate.pause_reason ? <span className="text-[10px] text-text-pg-dim">· {mandate.pause_reason}</span> : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => { setConfirming({ id: mandate.id, mode: mandate.paused ? "resume" : "pause" }); setError(""); setReason(""); setConfirmation(""); }}
                      className="inline-flex h-8 items-center gap-1.5 border border-border-pg px-2.5 text-xs text-text-pg hover:border-border-pg-strong rounded-lg"
                    >
                      {mandate.paused ? <><PlayCircle className="h-3.5 w-3.5" aria-hidden />{zh ? "恢复" : "Resume"}</> : <><CirclePause className="h-3.5 w-3.5" aria-hidden />{zh ? "暂停" : "Pause"}</>}
                    </button>
                  </div>
                </div>
                <dl className="grid gap-px bg-border-pg sm:grid-cols-2 lg:grid-cols-4">
                  <Field label={zh ? "单笔最大金额" : "Max per order"} value={money(mandate.max_per_order_notional, locale)} />
                  <Field label={zh ? "总敞口上限" : "Total exposure cap"} value={money(mandate.max_total_notional, locale)} />
                  <Field label={zh ? "单标的/仓位上限" : "Per-position cap"} value={money(mandate.max_position_notional, locale)} />
                  <Field label={zh ? "杠杆限制" : "Leverage limit"} value={`${mandate.max_leverage}x`} />
                  <Field label={zh ? "日亏损限制" : "Daily loss limit"} value={money(mandate.max_daily_loss, locale)} />
                  <Field label={zh ? "每日最大笔数" : "Max trades/day"} value={mandate.max_trades_per_day == null ? "--" : String(mandate.max_trades_per_day)} />
                  <Field label={zh ? "下单频率限制" : "Order frequency"} value={mandate.max_order_frequency_seconds == null ? "--" : `${mandate.max_order_frequency_seconds}s`} />
                  <Field label={zh ? "熔断状态" : "Kill switch"} value={mandate.kill_switch_state} />
                  <Field label={zh ? "审批状态" : "Approval"} value={mandate.approval_status} />
                  <Field label={zh ? "允许方向" : "Allowed side"} value={mandate.allowed_side} />
                  <Field label={zh ? "允许标的" : "Allowed symbols"} value={mandate.allowed_symbols.length ? mandate.allowed_symbols.join(", ") : "--"} />
                  <Field label={zh ? "最后审批时间" : "Approved at"} value={mandate.approved_at ? new Date(mandate.approved_at).toLocaleString(locale) : "--"} />
                </dl>
                {confirming?.id === mandate.id ? (
                  <div className="border-t border-status-warning p-3">
                    {confirming.mode === "pause" ? (
                      <>
                        <p className="text-xs text-status-warning">{zh ? "确认暂停此 Mandate？暂停会阻断该 Mandate 的所有后续交易。" : "Pause this mandate? Pausing blocks all further trading under this mandate."}</p>
                        <div className="mt-2 flex gap-2">
                          <input value={reason} onChange={(event) => setReason(event.target.value)} aria-label={zh ? "暂停原因" : "Pause reason"} placeholder={zh ? "必填：暂停原因" : "Required: pause reason"} className="min-w-0 flex-1 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm rounded-lg" />
                          <button type="button" onClick={() => void pause(mandate)} disabled={!reason.trim() || busy === `pause:${mandate.id}`} className="border border-status-warning px-3 py-2 text-xs font-semibold text-status-warning disabled:opacity-40 rounded-lg">{zh ? "确认暂停" : "Confirm pause"}</button>
                          <button type="button" onClick={() => setConfirming(null)} className="border border-border-pg px-3 py-2 text-xs rounded-lg">{zh ? "取消" : "Cancel"}</button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="text-xs text-status-warning">{zh ? "确认恢复此 Mandate？请输入至少 8 个字符的确认短语以继续。" : "Resume this mandate? Enter a confirmation phrase of at least 8 characters to continue."}</p>
                        <div className="mt-2 flex gap-2">
                          <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} aria-label={zh ? "确认短语" : "Confirmation phrase"} placeholder={zh ? "确认短语（至少 8 字符）" : "Confirmation phrase (min 8 chars)"} className="min-w-0 flex-1 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm rounded-lg" />
                          <button type="button" onClick={() => void resume(mandate)} disabled={confirmation.trim().length < 8 || busy === `resume:${mandate.id}`} className="border border-status-warning px-3 py-2 text-xs font-semibold text-status-warning disabled:opacity-40 rounded-lg">{zh ? "确认恢复" : "Confirm resume"}</button>
                          <button type="button" onClick={() => setConfirming(null)} className="border border-border-pg px-3 py-2 text-xs rounded-lg">{zh ? "取消" : "Cancel"}</button>
                        </div>
                      </>
                    )}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}

        {error ? <p className="text-xs text-status-negative" role="alert">{error}</p> : null}
      </div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-panel p-3">
      <dt className="text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</dt>
      <dd className="mt-1 text-sm font-medium tabular-nums text-text-pg">{value}</dd>
    </div>
  );
}

function formatError(reason: unknown, zh: boolean): string {
  const raw = String((reason as Error)?.message || reason);
  if (zh) return `操作失败：${raw}`;
  return `Operation failed: ${raw}`;
}
