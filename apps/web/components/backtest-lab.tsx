"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FlaskConical, Loader2, Play, RefreshCw, Sparkles } from "lucide-react";
import { BacktestTerminal } from "@/components/backtest-terminal";
import { type Locale, withLocale } from "@/i18n/routing";
import { API_URL, BacktestLabRun, BacktestLabSpec, BacktestLabStatus, exportBacktestLabRun, generateBacktestLabSpec, getBacktestLabRuns, getBacktestLabStatus, refreshBacktestLabData, runBacktestLab } from "@/lib/api";
import { PlotlyChart } from "@/components/plotly-chart";
import { getMessageNamespace } from "@/lib/translations";

type Copy = ReturnType<typeof getLabCopy>;
function getLabCopy(locale: Locale) {
  return getMessageNamespace(locale, "backtest-lab");
}

const WINDOW_OPTIONS = [
  { days: 365, key: "years1" as const },
  { days: 365 * 2, key: "years2" as const },
  { days: 365 * 3, key: "years3" as const },
];

function fmtPct(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function fmtNum(value: number | undefined, digits = 2) {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function BacktestLab({ locale }: { locale: Locale }) {
  const router = useRouter();
  const copy = useMemo(() => getLabCopy(locale), [locale]);
  const [status, setStatus] = useState<BacktestLabStatus | null>(null);
  const [runs, setRuns] = useState<BacktestLabRun[]>([]);
  const [selected, setSelected] = useState<BacktestLabRun | null>(null);
  const [idea, setIdea] = useState("");
  const [useMemory, setUseMemory] = useState(true);
  const [specText, setSpecText] = useState("");
  const [specMeta, setSpecMeta] = useState<{ fallback: boolean; context_notes: number } | null>(null);
  const [windowDays, setWindowDays] = useState(365 * 3);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  const parsedSpec = useMemo<BacktestLabSpec | null>(() => {
    if (!specText.trim()) return null;
    try {
      return JSON.parse(specText) as BacktestLabSpec;
    } catch {
      return null;
    }
  }, [specText]);

  const load = useCallback(async () => {
    const [statusResult, runsResult] = await Promise.all([getBacktestLabStatus(), getBacktestLabRuns(20)]);
    setStatus(statusResult);
    setRuns(runsResult.runs);
    if (!selected && runsResult.runs.length) setSelected(runsResult.runs[0]);
  }, [selected]);

  useEffect(() => {
    load().catch((reason: Error & { status?: number }) => {
      if (reason.status === 401) router.replace(`${withLocale(locale, "/login")}?returnTo=${encodeURIComponent(withLocale(locale, "/backtest"))}`);
      else setError(reason.message || copy.errors.loadFailed);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale]);

  useEffect(() => {
    if (!selected || (selected.status !== "queued" && selected.status !== "running")) return;
    const timer = window.setInterval(() => {
      getBacktestLabRuns(20).then((result) => {
        setRuns(result.runs);
        const latest = result.runs.find((item) => item.id === selected.id);
        if (latest) setSelected(latest);
      }).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selected]);

  const handleRefreshData = async () => {
    setRefreshing(true);
    setError("");
    try {
      const result = await refreshBacktestLabData();
      setStatus({ symbols: result.symbols, coverage: result.coverage, disclaimer: result.disclaimer });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy.errors.loadFailed);
    } finally {
      setRefreshing(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      const result = await generateBacktestLabSpec(idea, useMemory, locale);
      setSpecText(JSON.stringify(result.spec, null, 2));
      setSpecMeta(result.meta);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy.errors.generateFailed);
    } finally {
      setGenerating(false);
    }
  };

  const handleRun = async () => {
    if (!parsedSpec) return;
    setRunning(true);
    setError("");
    try {
      const result = await runBacktestLab(parsedSpec, windowDays, specMeta ? { generator: specMeta } : {});
      setSelected(result.run);
      const runsResult = await getBacktestLabRuns(20);
      setRuns(runsResult.runs);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : copy.errors.runFailed;
      setError(message.includes("BACKTEST_LAB_DAILY_LIMIT") ? copy.run.dailyLimit : message);
    } finally {
      setRunning(false);
    }
  };

  const handleExport = async (format: "json" | "csv") => {
    if (!selected || selected.is_legacy) return;
    setExporting(true);
    setError("");
    try {
      const result = await exportBacktestLabRun(selected.id, format);
      if (typeof window !== "undefined") window.open(`${API_URL}/backtest-lab/artifacts/${result.artifact.id}`, "_blank", "noopener,noreferrer");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const perf = selected?.performance;
  const isActive = selected?.status === "queued" || selected?.status === "running";

  return (
    <div className="space-y-6 py-4">
      <header className="space-y-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><FlaskConical className="h-6 w-6" />{copy.title}</h1>
        <p className="max-w-3xl text-sm leading-6 text-text-pg-muted">{copy.subtitle}</p>
      </header>

      {error ? <p className="border border-border-pg bg-bg-panel px-4 py-2.5 text-sm text-status-negative">{error}</p> : null}

      <section className="border border-border-pg bg-bg-panel p-4">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="font-semibold">{copy.coverage.title}</span>
          {(status?.symbols || ["BTC", "ETH"]).map((symbol) => {
            const item = status?.coverage?.[symbol];
            return (
              <span key={symbol} className="border border-border-pg px-2 py-1 text-text-pg-muted">
                {symbol}: {item ? `${item.bars} ${copy.coverage.bars}` : "—"}
                {item?.first_ts && item?.last_ts ? <span className="ml-1 text-text-pg-dim">{item.first_ts.slice(0, 10)} → {item.last_ts.slice(0, 10)}</span> : null}
              </span>
            );
          })}
          <button type="button" onClick={handleRefreshData} disabled={refreshing} className="ml-auto inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 font-medium transition hover:border-border-pg-strong disabled:opacity-50">
            {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {refreshing ? copy.coverage.refreshing : copy.coverage.refresh}
          </button>
        </div>
        {status && Object.values(status.coverage || {}).every((item) => !item.bars) ? <p className="mt-2 text-xs text-text-pg-dim">{copy.coverage.empty}</p> : null}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-4 border border-border-pg bg-bg-panel p-5">
          <h2 className="text-sm font-semibold">{copy.generate.title}</h2>
          <textarea value={idea} onChange={(event) => setIdea(event.target.value)} rows={3} placeholder={copy.generate.ideaPlaceholder} className="w-full border border-border-pg bg-bg-panel-muted p-3 text-sm outline-none focus:border-border-pg-strong" />
          <label className="flex items-center gap-2 text-xs text-text-pg-muted">
            <input type="checkbox" checked={useMemory} onChange={(event) => setUseMemory(event.target.checked)} className="accent-white" />
            {copy.generate.useMemory}
          </label>
          <button type="button" onClick={handleGenerate} disabled={generating} className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-2 text-sm font-semibold text-pg-black disabled:opacity-50">
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {generating ? copy.generate.generating : copy.generate.button}
          </button>
          {specMeta ? (
            <p className="text-[11px] text-text-pg-dim">
              {specMeta.fallback ? copy.generate.fallbackNotice : `${specMeta.context_notes} ${copy.generate.contextNotes}`}
            </p>
          ) : null}
        </section>

        <section className="space-y-4 border border-border-pg bg-bg-panel p-5">
          <h2 className="text-sm font-semibold">{copy.run.title}</h2>
          <label className="block text-xs text-text-pg-muted">{copy.run.specLabel}</label>
          <textarea value={specText} onChange={(event) => setSpecText(event.target.value)} rows={10} spellCheck={false} className="w-full border border-border-pg bg-bg-panel-muted p-3 font-mono text-[11px] leading-4 outline-none focus:border-border-pg-strong" />
          {specText && !parsedSpec ? <p className="text-xs text-status-negative">{copy.run.invalidSpec}</p> : null}
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="text-text-pg-muted">{copy.run.window}</span>
            {WINDOW_OPTIONS.map((option) => (
              <button key={option.days} type="button" onClick={() => setWindowDays(option.days)} className={`border px-2.5 py-1 ${windowDays === option.days ? "border-border-pg-strong bg-pg-white text-pg-black font-semibold" : "border-border-pg text-text-pg-muted"}`}>
                {copy.run[option.key]}
              </button>
            ))}
            <button type="button" onClick={handleRun} disabled={!parsedSpec || running} className="ml-auto inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-2 text-sm font-semibold text-pg-black disabled:opacity-50">
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {running ? copy.run.running : `${copy.run.button} · 50 ${copy.run.creditsHint}`}
            </button>
          </div>
        </section>
      </div>

      {selected ? (
        <section className="border border-border-pg bg-bg-panel p-5">
          <BacktestTerminal
            run={{ id: selected.id, status: selected.status, isLegacy: selected.is_legacy }}
            localeStr={locale}
          />
        </section>
      ) : null}

      {selected && perf ? (
        <section className="space-y-5 border border-border-pg bg-bg-panel p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">{copy.performance.title}: {selected.spec?.name}</h2>
            {isActive ? <span className="flex items-center gap-1 text-[11px] text-text-pg-muted"><Loader2 className="h-3 w-3 animate-spin" />{selected.status}</span> : null}
            {selected.is_legacy ? <span className="text-[11px] text-text-pg-dim">Legacy read-only result</span> : null}
            <span className="text-[11px] text-text-pg-dim">{selected.window.start?.slice(0, 10)} → {selected.window.end?.slice(0, 10)} · {selected.mode}</span>
          </div>
          <div className="grid grid-cols-2 gap-px border border-border-pg bg-border-pg md:grid-cols-4">
            {[
              [copy.performance.totalReturn, fmtPct(perf.total_return)],
              [copy.performance.sharpe, fmtNum(perf.sharpe)],
              [copy.performance.maxDrawdown, fmtPct(perf.max_drawdown ? -Math.abs(perf.max_drawdown) : perf.max_drawdown)],
              [copy.performance.winRate, fmtPct(perf.win_rate)],
              [copy.performance.tradeCount, String(perf.trade_count ?? 0)],
              [copy.performance.turnover, fmtNum(perf.turnover)],
              [copy.performance.exposure, fmtPct(perf.exposure_time)],
              [copy.performance.tailLoss, fmtPct(perf.tail_loss_95)],
            ].map(([label, value]) => (
              <div key={label} className="bg-bg-panel p-4">
                <div className="text-[10px] uppercase tracking-wide text-text-pg-dim">{label}</div>
                <div className="mt-1 text-lg font-semibold">{value}</div>
              </div>
            ))}
          </div>
          <div className="flex gap-2 text-xs"><button type="button" onClick={() => handleExport("json")} disabled={exporting || selected.status !== "completed"} className="inline-flex items-center gap-1 border border-border-pg px-2.5 py-1.5 hover:border-border-pg-strong disabled:opacity-50"><Download className="h-3 w-3" /> JSON · 50 credits</button><button type="button" onClick={() => handleExport("csv")} disabled={exporting || selected.status !== "completed"} className="border border-border-pg px-2.5 py-1.5 hover:border-border-pg-strong disabled:opacity-50">CSV · 50 credits</button></div>
          {selected.charts?.equity ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-text-pg-muted">{copy.performance.equityCurve}</h3>
              <PlotlyChart figure={selected.charts.equity} />
            </div>
          ) : null}
          {selected.charts?.drawdown ? <PlotlyChart figure={selected.charts.drawdown} className="h-56" /> : null}
          {selected.charts?.benchmark_comparison ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-text-pg-muted">Strategy vs benchmark</h3>
              <PlotlyChart figure={selected.charts.benchmark_comparison} />
            </div>
          ) : null}
          {selected.charts?.trades ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-text-pg-muted">Trade details</h3>
              <PlotlyChart figure={selected.charts.trades} className="h-56" />
            </div>
          ) : null}
          {selected.charts?.positions ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-text-pg-muted">Position changes</h3>
              <PlotlyChart figure={selected.charts.positions} className="h-56" />
            </div>
          ) : null}
          {selected.trades?.length ? (
            <details className="text-xs text-text-pg-muted">
              <summary className="cursor-pointer font-medium">Trade records ({selected.trades.length})</summary>
              <pre className="mt-2 max-h-64 overflow-auto border border-border-pg bg-bg-panel-muted p-3 text-[11px] leading-4">{JSON.stringify(selected.trades, null, 2)}</pre>
            </details>
          ) : null}
          {selected.positions?.length ? (
            <details className="text-xs text-text-pg-muted">
              <summary className="cursor-pointer font-medium">Position records ({selected.positions.length})</summary>
              <pre className="mt-2 max-h-64 overflow-auto border border-border-pg bg-bg-panel-muted p-3 text-[11px] leading-4">{JSON.stringify(selected.positions, null, 2)}</pre>
            </details>
          ) : null}
          {perf.per_asset ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-text-pg-muted">{copy.performance.perAsset}</h3>
              <div className="grid gap-px border border-border-pg bg-border-pg md:grid-cols-2">
                {Object.entries(perf.per_asset).map(([asset, metrics]) => (
                  <div key={asset} className="bg-bg-panel p-4 text-xs">
                    <div className="font-semibold">{asset}</div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-text-pg-muted">
                      <span>{copy.performance.totalReturn}: {fmtPct(metrics.total_return)}</span>
                      <span>{copy.performance.sharpe}: {fmtNum(metrics.sharpe)}</span>
                      <span>{copy.performance.maxDrawdown}: {fmtPct(metrics.max_drawdown ? -Math.abs(metrics.max_drawdown) : metrics.max_drawdown)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <details className="text-xs text-text-pg-muted">
            <summary className="cursor-pointer font-medium">{copy.performance.assumptions}</summary>
            <pre className="mt-2 overflow-x-auto border border-border-pg bg-bg-panel-muted p-3 text-[11px] leading-4">{JSON.stringify(selected.assumptions, null, 2)}</pre>
          </details>
        </section>
      ) : null}

      <section className="border border-border-pg bg-bg-panel p-5">
        <h2 className="mb-3 text-sm font-semibold">{copy.history.title}</h2>
        {runs.length === 0 ? <p className="text-xs text-text-pg-dim">{copy.history.empty}</p> : (
          <div className="divide-y divide-border-pg border border-border-pg">
            {runs.map((run) => (
              <button key={run.id} type="button" onClick={() => setSelected(run)} className={`flex w-full flex-wrap items-center gap-3 px-3 py-2.5 text-left text-xs transition hover:bg-bg-panel-muted ${selected?.id === run.id ? "bg-bg-panel-muted" : ""}`}>
                <span className="font-semibold">{run.spec?.name || run.id.slice(0, 8)}</span>
                <span className="text-text-pg-dim">{run.mode}</span>
                <span className="text-text-pg-dim">{run.status}</span>
                <span className="text-text-pg-muted">{copy.performance.totalReturn}: {fmtPct(run.performance?.total_return)}</span>
                <span className="text-text-pg-muted">{copy.performance.sharpe}: {fmtNum(run.performance?.sharpe)}</span>
                <span className="ml-auto text-text-pg-dim">{run.created_at.slice(0, 16).replace("T", " ")}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      <p className="text-[11px] leading-5 text-text-pg-dim">{copy.disclaimer}</p>
    </div>
  );
}
