import Link from "next/link";
import { ArrowRight, Radar } from "lucide-react";

import { Badge } from "@/components/puregamma";
import { API_URL } from "@/lib/api";
import { withLocale, type Locale } from "@/i18n/routing";

/**
 * Homepage entry for the Jev Trader live view.
 *
 * Three deliberate constraints:
 *
 * * It reads PureGamma's **own** snapshot endpoint, not the upstream demo. The
 *   upstream is a third party on a free tier; our homepage must not depend on
 *   it being reachable.
 * * Every failure path returns null. A preview is never worth taking the
 *   landing page down for, so the whole thing is wrapped and degrades to
 *   nothing.
 * * The honesty labels come from the snapshot's `model`/`dry_run` fields. The
 *   caption is never asserted here, because the upstream can change what it
 *   runs at any time.
 */
const FETCH_TIMEOUT_MS = 2500;

interface PreviewSnapshot {
  meta?: { model?: string | null; dry_run?: boolean | null };
  latest?: {
    block?: number;
    mid?: number | null;
    decision?: { action?: string | null; latency_ms?: number | null; late?: boolean };
  } | null;
}

async function loadSnapshot(): Promise<PreviewSnapshot | null> {
  try {
    const res = await fetch(`${API_URL}/jev-trader/snapshot`, {
      cache: "no-store",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as PreviewSnapshot;
  } catch {
    // Timeout, refused connection, malformed JSON: all equally "no preview".
    return null;
  }
}

export async function JevTraderPreview({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const snapshot = await loadSnapshot();
  if (!snapshot?.latest) return null;

  const meta = snapshot.meta ?? {};
  const latest = snapshot.latest;
  const decision = latest.decision ?? {};
  const isRealModel = !(meta.model ?? "").toLowerCase().includes("mock");
  const simulated = meta.dry_run === true;

  return (
    <section className="border border-border-pg bg-bg-panel p-6 md:p-8 rounded-2xl">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="cyan">
          <Radar className="h-3 w-3" />
          Jev Trader
        </Badge>
        <Badge tone={isRealModel ? "cyan" : "neutral"}>
          {isRealModel ? (zh ? "Jev 真实模型推理" : "Real Jev model") : zh ? "Mock 模型" : "Mock model"}
        </Badge>
        {simulated ? (
          <Badge tone="neutral">{zh ? "模拟交易" : "Simulated trading"}</Badge>
        ) : null}
      </div>

      <h2 className="mt-5 text-xl font-semibold md:text-2xl">
        {zh ? "实时 AI 决策看板" : "Real-time AI decision dashboard"}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-text-pg-muted">
        {zh
          ? "每个 Monad 区块一次 Jev 评估。行情为真实链上数据，交易为模拟，无真实资金。"
          : "One Jev evaluation per Monad block. Prices are live on-chain data; trading is simulated with no real funds."}
      </p>

      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <span className="text-text-pg-muted">
          {zh ? "最新区块" : "Latest block"}:{" "}
          <span className="font-medium tabular-nums text-text-pg">{latest.block?.toLocaleString() ?? "—"}</span>
        </span>
        <span className="text-text-pg-muted">
          {zh ? "决策" : "Decision"}:{" "}
          <span className="font-medium text-text-pg">
            {decision.late ? (zh ? "迟到" : "late") : decision.action ?? "—"}
          </span>
        </span>
        <span className="text-text-pg-muted">
          {zh ? "推理耗时" : "Latency"}:{" "}
          <span className="font-medium tabular-nums text-text-pg">
            {decision.latency_ms != null ? `${decision.latency_ms} ms` : "—"}
          </span>
        </span>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href={withLocale(locale, "/jev-trader")}
          className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-3 text-sm font-semibold text-pg-black rounded-lg"
        >
          {zh ? "进入实时展示" : "Open live dashboard"} <ArrowRight className="h-4 w-4" />
        </Link>
        <Link
          href={withLocale(locale, "/api")}
          className="inline-flex items-center gap-2 border border-border-pg px-4 py-3 text-sm font-semibold text-text-pg hover:border-border-pg-strong rounded-lg"
        >
          {zh ? "调用 Jev API" : "Use the Jev API"}
        </Link>
      </div>
    </section>
  );
}
