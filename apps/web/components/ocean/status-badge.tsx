"use client";

import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, CircleDashed, CircleX, Info, Loader2 } from "lucide-react";

export type ResearchStatus = "queued" | "preparing" | "running" | "validating" | "completed" | "degraded" | "failed" | "canceled" | "timed_out" | "pending";
export type TradingEnvironment = "PAPER" | "SHADOW" | "LIVE_DISABLED" | "LIVE";
export type DataFreshness = "fresh" | "stale" | "reconciled" | "needs_review" | "unknown";

export type BadgeTone = "neutral" | "info" | "positive" | "warning" | "negative";

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: "border-border-pg bg-bg-panel-muted text-text-pg-muted",
  info: "border-ocean-line bg-ocean-blue-muted text-ocean-cyan",
  positive: "border-border-pg bg-bg-panel-muted text-status-positive",
  warning: "border-border-pg bg-bg-panel-muted text-status-warning",
  negative: "border-border-pg bg-bg-panel-muted text-status-negative",
};

const TONE_ICON: Record<BadgeTone, typeof Info> = {
  neutral: CircleDashed,
  info: Info,
  positive: CircleCheck,
  warning: CircleAlert,
  negative: CircleX,
};

const RESEARCH_META: Record<ResearchStatus, { en: string; zh: string; tone: BadgeTone }> = {
  queued: { en: "Queued", zh: "排队中", tone: "neutral" },
  pending: { en: "Pending", zh: "待处理", tone: "neutral" },
  preparing: { en: "Preparing", zh: "准备中", tone: "info" },
  running: { en: "Running", zh: "运行中", tone: "info" },
  validating: { en: "Validating", zh: "验证中", tone: "info" },
  completed: { en: "Completed", zh: "已完成", tone: "positive" },
  degraded: { en: "Degraded", zh: "已降级", tone: "warning" },
  failed: { en: "Failed", zh: "失败", tone: "negative" },
  canceled: { en: "Canceled", zh: "已取消", tone: "neutral" },
  timed_out: { en: "Timed out", zh: "已超时", tone: "negative" },
};

const TRADING_META: Record<TradingEnvironment, { en: string; zh: string; tone: BadgeTone }> = {
  PAPER: { en: "PAPER", zh: "模拟盘", tone: "info" },
  SHADOW: { en: "SHADOW", zh: "影子盘", tone: "info" },
  LIVE_DISABLED: { en: "LIVE DISABLED", zh: "实盘未启用", tone: "warning" },
  LIVE: { en: "LIVE", zh: "实盘", tone: "warning" },
};

const DATA_META: Record<DataFreshness, { en: string; zh: string; tone: BadgeTone }> = {
  fresh: { en: "Fresh", zh: "最新", tone: "positive" },
  stale: { en: "Stale", zh: "数据过期", tone: "warning" },
  reconciled: { en: "Reconciled", zh: "已对账", tone: "positive" },
  needs_review: { en: "Needs Review", zh: "待复核", tone: "warning" },
  unknown: { en: "Unknown", zh: "未知", tone: "neutral" },
};

/**
 * Unified status badge. Text is always present — never color-only.
 * Unknown values render neutrally with the raw value instead of crashing.
 */
export function StatusBadge({ domain, value, locale, className = "" }: {
  domain: "research" | "trading" | "data";
  value: string;
  locale: "en" | "zh";
  className?: string;
}) {
  const zh = locale === "zh";
  let meta: { en: string; zh: string; tone: BadgeTone } | undefined;
  if (domain === "research") meta = RESEARCH_META[value as ResearchStatus];
  else if (domain === "trading") meta = TRADING_META[value as TradingEnvironment];
  else meta = DATA_META[value as DataFreshness];
  const label = meta ? (zh ? meta.zh : meta.en) : value;
  const tone = meta?.tone ?? "neutral";
  const Icon = TONE_ICON[tone];
  return (
    <span className={`inline-flex items-center gap-1 border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${TONE_CLASS[tone]} ${className}`}>
      <Icon className="h-3 w-3" aria-hidden />
      <span>{label}</span>
    </span>
  );
}

export function StatusBadgeWithPulse({ domain, value, locale, className = "" }: { domain: "research" | "trading" | "data"; value: string; locale: "en" | "zh"; className?: string }) {
  const running = domain === "research" && (value === "running" || value === "validating");
  return <StatusBadge domain={domain} value={value} locale={locale} className={`${running ? "ocean-stage-active" : ""} ${className}`} />;
}

export function CapabilityBadge({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center gap-1 border border-border-pg bg-bg-panel-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-text-pg-muted">{children}</span>;
}

export function LoadingBadge({ locale }: { locale: "en" | "zh" }) {
  return (
    <span className="inline-flex items-center gap-1 border border-border-pg bg-bg-panel-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-text-pg-muted">
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
      {locale === "zh" ? "加载中" : "Loading"}
    </span>
  );
}
