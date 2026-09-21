"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";

import { Badge, MetricCard, ResearchCard } from "@/components/puregamma";
import { getJevAdvisoryStatus, type JevAdvisoryStatus } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

function percent(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
}

function millis(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value} ms` : "—";
}

export function JevAdvisoryConsole({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [state, setState] = useState<JevAdvisoryStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setState(await getJevAdvisoryStatus());
    } catch {
      // The user may be signed out or the API may be temporarily unavailable.
      // We leave the previous verified state intact and show an honest fallback.
      setState({
        available: false,
        status: "unavailable",
        reason: zh ? "无法读取顾问遥测数据。" : "Advisory telemetry could not be read.",
        mode: "ADVISORY_ONLY",
        execution: "DISABLED",
      });
    } finally {
      setLoading(false);
    }
  }, [zh]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const fresh = state?.available && state.status === "fresh";
  const probabilities = state?.probabilities;

  return <div className="space-y-5">
    <ResearchCard className="overflow-hidden p-0">
      <div className="border-b border-border-pg p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase text-text-pg-muted">TypeSafe JEV · Advisory telemetry</div>
            <h2 className="mt-2 text-xl font-semibold">{zh ? "Jev 顾问状态" : "Jev advisory status"}</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-pg-muted">
              {zh ? "只展示经运行时校验的短时建议。它不能生成订单、不能批准交易，也不会阻止减仓或退出。" : "Only short-lived observations validated by the runtime appear here. They cannot create or approve an order, and never block a reduction or exit."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={fresh ? "emerald" : "neutral"}>{fresh ? (zh ? "已验证 · 新鲜" : "verified · fresh") : (zh ? "不可用 / 未验证" : "unavailable / unverified")}</Badge>
            <button type="button" aria-label={zh ? "刷新 Jev 状态" : "Refresh Jev status"} onClick={() => void refresh()} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border-pg px-2 text-xs text-text-pg-muted hover:text-text-pg">
              <RefreshCw className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />{zh ? "刷新" : "Refresh"}
            </button>
          </div>
        </div>
      </div>

      {!fresh ? <div className="flex gap-3 p-5 text-sm text-text-pg-muted">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-warning" />
        <p>{state?.reason ?? (zh ? "正在获取经验证的运行时遥测。不会用历史演示数据或估算值填充。" : "Fetching validated runtime telemetry. Historical demo data and estimates are never substituted.")}</p>
      </div> : <div className="p-5">
        <div className="grid gap-px border border-border-pg bg-border-pg sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label={zh ? "建议方向" : "Advisory choice"} value={(state.choice ?? "—").toUpperCase()} />
          <MetricCard label={zh ? "模型置信度" : "Provider confidence"} value={percent(state.provider_confidence)} />
          <MetricCard label={zh ? "接收延迟" : "Receive age"} value={millis(state.age_ms)} />
          <MetricCard label={zh ? "剩余有效期" : "TTL remaining"} value={millis(state.ttl_ms)} />
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {(["up", "down", "neutral"] as const).map((choice) => (
            <div key={choice} className="rounded-lg border border-border-pg bg-bg-panel-muted p-3">
              <div className="flex items-center justify-between text-[11px] uppercase text-text-pg-muted"><span>{choice}</span>{state.choice === choice ? <Activity className="h-3.5 w-3.5 text-accent-pg" /> : null}</div>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{percent(probabilities?.[choice])}</p>
            </div>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-text-pg-muted">
          <span>{zh ? "模型" : "Model"}: {state.model}</span>
          <span>{zh ? "标的" : "Instrument"}: {state.instrument}</span>
          <span>{zh ? "输入 / 输出 token" : "Input / output tokens"}: {state.input_tokens ?? "—"} / {state.output_tokens ?? "—"}</span>
        </div>
      </div>}
    </ResearchCard>

    <ResearchCard className="flex gap-3 p-5 text-sm text-text-pg-muted">
      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-status-positive" />
      <p>{zh ? "执行边界：确定性策略、风控、授权、账本与交易所网关始终优先。Jev 缺失、过期或校验失败时，只会阻止新的风险敞口；已有减仓不受影响。" : "Execution boundary: deterministic strategy, risk, mandate, ledger, and venue gateway remain authoritative. Missing, stale, or invalid Jev only holds new exposure; an owned reduction remains independent."}</p>
    </ResearchCard>
  </div>;
}
