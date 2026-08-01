"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bell, Download, FileDown, MessageCircleQuestion, RefreshCw } from "lucide-react";
import { Badge, EmptyState, ResearchCard } from "@/components/puregamma";
import { PlotlyChart } from "@/components/plotly-chart";
import { getMessageNamespace } from "@/lib/translations";
import { getOptionsSurface, getOptionsSurfaceTickers, type LongGammaCandidate, type OptionSurfaceResponse } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

type SurfaceType = "mark_iv" | "mark_price" | "gamma" | "theta" | "vega" | "spread_pct";

const SURFACE_TYPES: SurfaceType[] = ["mark_iv", "mark_price", "gamma", "theta", "spread_pct"];

function surfaceLabel(copy: { type: Record<string, string> }, type: SurfaceType) {
  return copy.type[type] || type;
}

function zFromCandidate(candidate: LongGammaCandidate, type: SurfaceType) {
  if (type === "mark_iv") return candidate.mark_iv ?? 0;
  if (type === "mark_price") return candidate.mark_price ?? 0;
  const greeks = candidate.greeks || {};
  if (type === "gamma") return greeks.gamma ?? 0;
  if (type === "theta") return greeks.theta ?? 0;
  if (type === "spread_pct") return candidate.spread_pct ?? 0;
  return 0;
}

export function OptionsSurface({ locale, initialCurrency = "BTC" }: { locale: Locale; initialCurrency?: string }) {
  const zh = locale === "zh";
  const copy = useMemo(() => getMessageNamespace(locale, "options-surface"), [locale]);
  const [currency, setCurrency] = useState(initialCurrency);
  const [surfaceType, setSurfaceType] = useState<SurfaceType>("mark_iv");
  const [data, setData] = useState<OptionSurfaceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [tickers, setTickers] = useState<{ symbol: string; provider: string; label: string; market_cap: string }[]>([]);

  const loadTickers = useCallback(async () => {
    const result = await getOptionsSurfaceTickers(locale);
    if (result.tickers.length) setTickers(result.tickers);
  }, [locale]);

  const load = useCallback(async (symbol: string, type: SurfaceType) => {
    setLoading(true);
    const result = await getOptionsSurface(symbol, type);
    setData(result);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadTickers();
  }, [loadTickers]);

  useEffect(() => {
    void load(currency, surfaceType);
  }, [currency, surfaceType, load]);

  const traces = useMemo(() => {
    if (!data || !data.surface.rows.length) return [];
    const { surface, candidates } = data;
    const traces: Record<string, unknown>[] = [];
    traces.push({
      type: "mesh3d",
      x: surface.x,
      y: surface.y,
      z: surface.z,
      intensity: surface.z,
      colorscale: "Viridis",
      opacity: 0.85,
      name: copy.chart.surfaceName,
      hovertemplate: "S/K=%{x:.3f}<br>DTE=%{y:.1f}<br>Z=%{z:.4f}<extra></extra>",
    });
    if (candidates.length && surface.underlying_price > 0) {
      traces.push({
        type: "scatter3d",
        mode: "markers",
        x: candidates.map((item) => item.strike / surface.underlying_price),
        y: candidates.map((item) => item.days_to_expiry),
        z: candidates.map((item) => zFromCandidate(item, surface.type)),
        marker: {
          size: candidates.map((item) => Math.max(4, Math.min(24, item.open_interest / 50))),
          color: candidates.map((item) => item.research_score),
          colorscale: "Hot",
          showscale: true,
          colorbar: { title: copy.chart.scoreColorbar },
        },
        text: candidates.map((item) => item.instrument),
        name: copy.chart.candidatesName,
        hovertemplate: "<b>%{text}</b><br>S/K=%{x:.3f}<br>DTE=%{y:.1f}<br>Score=%{marker.color:.1f}<extra></extra>",
      });
    }
    return traces;
  }, [data, copy]);

  const layout = useMemo(() => {
    if (!data) return undefined;
    return {
      scene: {
        xaxis: { title: { text: copy.chart.xAxis } },
        yaxis: { title: { text: copy.chart.yAxis } },
        zaxis: { title: { text: surfaceLabel(copy, data.surface.type) } },
        camera: { eye: { x: 1.8, y: 1.8, z: 1.2 } },
      },
      margin: { t: 0, r: 0, b: 0, l: 0 },
      paper_bgcolor: "rgba(0,0,0,0)",
      height: 540,
    };
  }, [data, copy]);

  const insights = data?.insights;

  return (
    <ResearchCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-eyebrow uppercase text-text-pg-muted">{copy.eyebrow}</div>
          <h2 className="mt-1 font-semibold">{copy.title}</h2>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-text-pg-muted">{copy.subtitle}</p>
        </div>
        <div className="flex items-center gap-2"><Badge tone={data?.status === "HEALTHY" ? "emerald" : "amber"}>{data?.status ?? "-"}</Badge><Badge tone="neutral">{data?.provider ?? "-"}</Badge></div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {tickers.map((item) => (
          <button key={item.symbol} type="button" disabled={loading} onClick={() => setCurrency(item.symbol)} title={item.market_cap} className={`border px-3 py-1.5 text-sm disabled:opacity-50 ${currency === item.symbol ? "border-border-pg-strong bg-bg-panel-muted font-semibold" : "border-border-pg text-text-pg-muted"}`}>{item.symbol}</button>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {SURFACE_TYPES.map((type) => (
          <button key={type} type="button" disabled={loading} onClick={() => setSurfaceType(type)} className={`border px-2.5 py-1 text-xs disabled:opacity-50 ${surfaceType === type ? "border-border-pg-strong bg-pg-white font-semibold text-pg-black" : "border-border-pg text-text-pg-muted"}`}>{surfaceLabel(copy, type)}</button>
        ))}
        <button type="button" disabled={loading} onClick={() => void load(currency, surfaceType)} className="ml-auto inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1 text-xs text-text-pg-muted disabled:opacity-50"><RefreshCw className="h-3 w-3" />{copy.refresh}</button>
      </div>

      {loading ? <div className="mt-4 h-72 border border-border-pg bg-bg-panel-muted" /> : null}
      {!loading && data && data.surface.rows.length ? <div className="mt-4"><PlotlyChart figure={{ data: traces, layout }} className="h-[540px]" /></div> : null}
      {!loading && data && (!data.surface.rows.length || data.error) ? (
        <div className="mt-4"><EmptyState title={data.error ? copy.emptyErrorTitle : copy.emptyTitle} description={data.error || copy.emptyDescription} /></div>
      ) : null}

      {!loading && data && data.surface.rows.length ? (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border border-border-pg bg-bg-panel-muted p-3 text-xs">
          <span>{copy.insights.atm30}: <strong>{insights?.atm_iv != null ? `${(insights.atm_iv * 100).toFixed(2)}%` : "-"}</strong></span>
          <span>{copy.insights.put25}: <strong>{insights?.put25_iv != null ? `${(insights.put25_iv * 100).toFixed(2)}%` : "-"}</strong></span>
          <span>{copy.insights.call25}: <strong>{insights?.call25_iv != null ? `${(insights.call25_iv * 100).toFixed(2)}%` : "-"}</strong></span>
          <span>{copy.insights.skew}: <strong className={insights?.skew_pct != null && insights.skew_pct > 0.05 ? "text-status-negative" : ""}>{insights?.skew_pct != null ? `${(insights.skew_pct * 100).toFixed(2)}pp` : "-"}</strong></span>
          <span>{copy.insights.underlying}: <strong>{insights?.underlying_price ? insights.underlying_price.toLocaleString(locale) : "-"}</strong></span>
          <span className="ml-auto flex items-center gap-2"><button type="button" className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-text-pg-muted hover:border-border-pg-strong" title={copy.insights.alertTitle}><Bell className="h-3 w-3" />{copy.insights.alert}</button><button type="button" className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-text-pg-muted hover:border-border-pg-strong" title={copy.insights.exportTitle}><Download className="h-3 w-3" />{copy.insights.export}</button><button type="button" className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-text-pg-muted hover:border-border-pg-strong" title={copy.insights.agentTitle}><MessageCircleQuestion className="h-3 w-3" />{copy.insights.askAgent}</button></span>
        </div>
      ) : null}

      {data && data.surface.rows.length && data.surface.type !== "mark_iv" ? (
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-text-pg-dim"><AlertTriangle className="h-3 w-3" />{copy.nonIvNotice}</p>
      ) : null}
      {data && data.surface.rows.length ? <p className="mt-2 flex items-center gap-1.5 text-[11px] text-text-pg-dim"><FileDown className="h-3 w-3" />{copy.barsNote}</p> : null}
    </ResearchCard>
  );
}
