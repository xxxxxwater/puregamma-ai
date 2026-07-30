"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, RefreshCw } from "lucide-react";
import { Badge, ResearchCard, StatusDot } from "@/components/puregamma";
import { approveGatewayPrice, getGatewayAdminProviders, getGatewayMetrics, getGatewayPendingPrices, getGatewayPricingPolicy, syncGatewayProviders, updateGatewayMarkup, type GatewayAdminProvider, type GatewayMetrics, type GatewayPriceRevision } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const money = (value: string) => `$${Number(value || 0).toFixed(4)}`;

export function GatewayAdminConsole({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [providers, setProviders] = useState<GatewayAdminProvider[]>([]);
  const [revisions, setRevisions] = useState<GatewayPriceRevision[]>([]);
  const [metrics, setMetrics] = useState<GatewayMetrics | null>(null);
  const [markup, setMarkup] = useState("3000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      const [providerData, priceData, metricData, policyData] = await Promise.all([getGatewayAdminProviders(), getGatewayPendingPrices(), getGatewayMetrics(), getGatewayPricingPolicy()]);
      setProviders(providerData.providers); setRevisions(priceData.revisions); setMetrics(metricData); setMarkup(String(policyData.policy.markup_bps));
    } catch {
      setError(zh ? "无法读取 Gateway 管理数据。" : "Unable to load Gateway administration data.");
    }
  }, [zh]);
  useEffect(() => { void load(); }, [load]);
  const sync = async () => { setBusy(true); try { await syncGatewayProviders(); await load(); } catch { setError(zh ? "同步失败。" : "Sync failed."); } finally { setBusy(false); } };
  const approve = async (id: string) => { setBusy(true); try { await approveGatewayPrice(id); await load(); } catch { setError(zh ? "批准失败。" : "Approval failed."); } finally { setBusy(false); } };
  const saveMarkup = async () => { const parsed = Number(markup); if (!Number.isInteger(parsed) || parsed < 0 || parsed > 100000) { setError(zh ? "Markup 必须为 0–100000 个基点。" : "Markup must be 0–100000 basis points."); return; } setBusy(true); try { await updateGatewayMarkup(parsed); await load(); } catch { setError(zh ? "保存失败。" : "Save failed."); } finally { setBusy(false); } };
  return <ResearchCard>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-eyebrow uppercase text-text-pg-muted">PureGamma API</div><h2 className="mt-1 font-semibold">{zh ? "Gateway 定价与 Provider" : "Gateway pricing & providers"}</h2><p className="mt-1 text-sm text-text-pg-muted">{zh ? "同步只创建待审核更新；批准后即时生效。" : "Sync creates pending updates only; approval takes effect immediately."}</p></div><button type="button" disabled={busy} onClick={() => void sync()} className="inline-flex items-center gap-2 border border-border-pg px-3 py-2 text-sm disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />{zh ? "立即同步" : "Sync now"}</button></div>
    {error ? <p className="mt-3 text-sm text-status-negative">{error}</p> : null}
    <div className="mt-4 grid gap-3 md:grid-cols-4"><div className="border border-border-pg bg-bg-panel-muted p-3"><div className="text-xs text-text-pg-muted">{zh ? "收入" : "Revenue"}</div><div className="mt-1 font-semibold">{money(metrics?.revenue_usd || "0")}</div></div><div className="border border-border-pg bg-bg-panel-muted p-3"><div className="text-xs text-text-pg-muted">{zh ? "成本" : "Cost"}</div><div className="mt-1 font-semibold">{money(metrics?.provider_cost_usd || "0")}</div></div><div className="border border-border-pg bg-bg-panel-muted p-3"><div className="text-xs text-text-pg-muted">{zh ? "利润" : "Profit"}</div><div className="mt-1 font-semibold">{money(metrics?.profit_usd || "0")}</div></div><div className="border border-border-pg bg-bg-panel-muted p-3"><div className="text-xs text-text-pg-muted">{zh ? "请求" : "Requests"}</div><div className="mt-1 font-semibold">{metrics?.requests || 0}</div></div></div>
    <div className="mt-4 grid gap-4 xl:grid-cols-2"><div><h3 className="mb-2 text-sm font-semibold">{zh ? "Provider 健康状态" : "Provider health"}</h3><div className="space-y-2">{providers.map((provider) => <div key={provider.id} className="flex items-center justify-between border border-border-pg bg-bg-panel-muted p-2 text-sm"><div><div className="font-medium">{provider.display_name}</div><div className="text-xs text-text-pg-muted">{provider.models} models · {provider.last_error || "—"}</div></div><Badge tone={provider.health_status === "healthy" ? "emerald" : provider.health_status === "unhealthy" ? "red" : "amber"}><StatusDot tone={provider.health_status === "healthy" ? "emerald" : provider.health_status === "unhealthy" ? "red" : "amber"} /> {provider.health_status}</Badge></div>)}{!providers.length ? <p className="text-sm text-text-pg-muted">{zh ? "尚未初始化 Provider。" : "Providers are not initialized yet."}</p> : null}</div></div><div><h3 className="mb-2 text-sm font-semibold">{zh ? "默认 Markup" : "Default markup"}</h3><div className="flex gap-2"><input value={markup} onChange={(event) => setMarkup(event.target.value)} inputMode="numeric" className="min-w-0 flex-1 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" aria-label="Markup basis points" /><button type="button" onClick={() => void saveMarkup()} disabled={busy} className="border border-border-pg px-3 py-2 text-sm disabled:opacity-50">{zh ? "保存" : "Save"}</button></div><p className="mt-2 text-xs text-text-pg-muted">3000 bp = 30%. {zh ? "保存时会基于官方价格立即重新计算所有已激活模型。" : "Saving immediately recalculates every active model from its official price."}</p></div></div>
    <div className="mt-4"><h3 className="mb-2 text-sm font-semibold">{zh ? "待确认官方价格" : "Pending official prices"}</h3><div className="space-y-2">{revisions.map((revision) => <div key={revision.id} className="flex flex-wrap items-center justify-between gap-3 border border-status-warning/50 bg-bg-panel-muted p-3 text-sm"><div className="min-w-0"><div className="font-mono text-xs">{revision.model_id}</div><div className="mt-1 text-xs text-text-pg-muted">{revision.source_reference || revision.source_type} · {new Date(revision.synced_at).toLocaleString(locale)}</div><div className="mt-1 max-w-[620px] truncate text-xs text-text-pg-muted">official: {JSON.stringify(revision.official_prices)} → final: {JSON.stringify(revision.final_prices)}</div></div><button type="button" disabled={busy} onClick={() => void approve(revision.id)} className="inline-flex items-center gap-1 border border-status-positive px-3 py-2 text-sm text-status-positive disabled:opacity-50"><Check className="h-4 w-4" />{zh ? "确认生效" : "Approve"}</button></div>)}{!revisions.length ? <p className="text-sm text-text-pg-muted">{zh ? "没有待确认的价格变更。" : "No price changes await approval."}</p> : null}</div></div>
  </ResearchCard>;
}
