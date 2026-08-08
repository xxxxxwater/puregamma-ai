"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip } from "@/components/charts";
import { EmptyState, MetricCard, ResearchCard } from "@/components/puregamma";
import { getGatewayUsage, type GatewayUsage, type GatewayUsageBucket, type GatewayUsageBreakdownRow } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const grid = "var(--border)";
const text = "var(--muted)";
const white = "var(--foreground)";
const positive = "var(--positive)";
const negative = "var(--negative)";
const warning = "var(--warning)";
const positiveFill = "color-mix(in srgb, var(--positive) 12%, transparent)";
const whiteFill = "color-mix(in srgb, var(--foreground) 10%, transparent)";
const warningFill = "color-mix(in srgb, var(--warning) 12%, transparent)";

type Props = { locale: Locale; initialUsage: GatewayUsage };

const money = (value: string) => `$${Number(value || 0).toFixed(4)}`;
const num = (value: number) => value.toLocaleString();

function UsageTooltip({ active, payload, label, prefix }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string; prefix?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-border-pg bg-bg-panel px-3 py-2 text-xs rounded-lg">
      <div className="mb-1 text-text-pg-muted">{label}</div>
      {payload.map((item) => <div key={item.name} className="text-text-pg">{item.name}: {prefix || ""}{num(Number(item.value))}</div>)}
    </div>
  );
}

type Preset = "24h" | "7d" | "30d" | "90d" | "custom";

export function UsagePanel({ locale, initialUsage }: Props) {
  const zh = locale === "zh";
  const [preset, setPreset] = useState<Preset>("7d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [usage, setUsage] = useState(initialUsage);
  const [loading, setLoading] = useState(false);
  const [modelFilter, setModelFilter] = useState<string | null>(null);
  const [keyFilter, setKeyFilter] = useState<string | null>(null);

  const now = new Date();
  const presets: { id: Preset; label: string; days: number }[] = [
    { id: "24h", label: zh ? "24 小时" : "24h", days: 1 },
    { id: "7d", label: zh ? "7 天" : "7d", days: 7 },
    { id: "30d", label: zh ? "30 天" : "30d", days: 30 },
    { id: "90d", label: zh ? "90 天" : "90d", days: 90 },
  ];

  const applyRange = async (start: Date, end: Date, granularity: "hour" | "day") => {
    setLoading(true);
    const result = await getGatewayUsage(locale, {
      start: start.toISOString().slice(0, 19) + "+00:00",
      end: end.toISOString().slice(0, 19) + "+00:00",
      granularity,
      model: modelFilter || undefined,
      api_key_id: keyFilter || undefined,
    });
    setUsage(result);
    setLoading(false);
  };

  const selectPreset = (id: Preset) => {
    setPreset(id);
    const days = presets.find((item) => item.id === id)?.days ?? 7;
    const end = new Date(now.getTime());
    const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
    void applyRange(start, end, id === "24h" ? "hour" : "day");
  };

  const applyCustom = () => {
    if (!customStart || !customEnd) return;
    const start = new Date(customStart);
    const end = new Date(customEnd);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start >= end) return;
    setPreset("custom" as Preset);
    const spanHours = (end.getTime() - start.getTime()) / (60 * 60 * 1000);
    void applyRange(start, end, spanHours <= 48 ? "hour" : "day");
  };

  useEffect(() => {
    void applyRange(new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000), now, "day");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buckets: GatewayUsageBucket[] = useMemo(() => usage?.buckets ?? [], [usage]);
  const totals = useMemo(() => usage?.totals ?? { requests: 0, success: 0, errors: 0, input_tokens: 0, output_tokens: 0, cache_tokens: 0, reasoning_tokens: 0, avg_latency_ms: 0, max_latency_ms: 0, cost_usd: "0" }, [usage]);
  const byModel = useMemo(() => usage?.by_model ?? [], [usage]);
  const byKey = useMemo(() => usage?.by_key ?? [], [usage]);

  const tokenSeries = buckets.map((bucket) => ({
    date: new Date(bucket.bucket).toLocaleString(locale, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
    input: bucket.input_tokens,
    output: bucket.output_tokens,
    cache: bucket.cache_tokens,
  }));
  const requestSeries = buckets.map((bucket) => ({
    date: new Date(bucket.bucket).toLocaleString(locale, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
    success: bucket.success,
    errors: bucket.errors,
  }));
  const costSeries = buckets.map((bucket) => ({
    date: new Date(bucket.bucket).toLocaleString(locale, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
    cost: Number(bucket.cost_usd || 0),
  }));
  const latencySeries = buckets.map((bucket) => ({
    date: new Date(bucket.bucket).toLocaleString(locale, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
    latency: bucket.avg_latency_ms,
  }));

  const models = useMemo(() => {
    const names = Array.from(new Set(byModel.map((row) => row.model).filter(Boolean) as string[]));
    return names;
  }, [byModel]);
  const keys = useMemo(() => byKey.filter((row): row is GatewayUsageBreakdownRow & { api_key_id: string } => Boolean(row.api_key_id)), [byKey]);

  const selectModel = (model: string | null) => {
    setModelFilter(model);
    if (preset === "custom") {
      if (customStart && customEnd) void applyCustom();
    } else {
      const days = presets.find((item) => item.id === preset)?.days ?? 7;
      const end = new Date(now.getTime());
      void applyRange(new Date(end.getTime() - days * 24 * 60 * 60 * 1000), end, preset === "24h" ? "hour" : "day");
    }
  };

  const selectKey = (keyId: string | null) => {
    setKeyFilter(keyId);
    if (preset === "custom") {
      if (customStart && customEnd) void applyCustom();
    } else {
      const days = presets.find((item) => item.id === preset)?.days ?? 7;
      const end = new Date(now.getTime());
      void applyRange(new Date(end.getTime() - days * 24 * 60 * 60 * 1000), end, preset === "24h" ? "hour" : "day");
    }
  };

  const hasData = buckets.some((bucket) => bucket.requests > 0);
  const totalTokens = totals.input_tokens + totals.output_tokens + totals.cache_tokens;

  return <div className="space-y-5">
    {usage?.unavailable ? <div className="border border-status-warning bg-bg-panel p-4 text-sm text-text-pg-muted rounded-xl">{zh ? "用量数据暂不可用。请确认网关已启用并使用已登录账户访问。" : "Usage data is unavailable. Confirm that the gateway is enabled and you are signed in."}</div> : null}

    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="text-eyebrow uppercase text-text-pg-muted">Usage analytics</div>
        <h2 className="mt-1 font-semibold">{zh ? "用量" : "Usage"}</h2>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        {presets.map((item) => <button key={item.id} type="button" disabled={loading} onClick={() => selectPreset(item.id)} className={`border px-3 py-1.5 text-sm disabled:opacity-50  rounded-lg${preset === item.id ? "border-text-pg bg-text-pg font-semibold text-bg-panel" : "border-border-pg bg-bg-panel-muted"}`}>{item.label}</button>)}
        <div className="flex items-end gap-2">
          <label className="text-xs text-text-pg-muted">{zh ? "起" : "From"}<input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} className="mt-1 block border border-border-pg bg-bg-panel-muted px-2 py-1.5 text-sm rounded-lg" /></label>
          <label className="text-xs text-text-pg-muted">{zh ? "止" : "To"}<input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} className="mt-1 block border border-border-pg bg-bg-panel-muted px-2 py-1.5 text-sm rounded-lg" /></label>
          <button type="button" disabled={loading || !customStart || !customEnd} onClick={applyCustom} className="border border-border-pg bg-bg-panel-muted px-3 py-1.5 text-sm disabled:opacity-50 rounded-lg">{zh ? "应用" : "Apply"}</button>
        </div>
        <select value={modelFilter ?? ""} onChange={(event) => selectModel(event.target.value || null)} className="border border-border-pg bg-bg-panel-muted px-2 py-1.5 text-sm rounded-lg" aria-label="Filter by model">
          <option value="">{zh ? "全部模型" : "All models"}</option>
          {models.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <select value={keyFilter ?? ""} onChange={(event) => selectKey(event.target.value || null)} className="border border-border-pg bg-bg-panel-muted px-2 py-1.5 text-sm rounded-lg" aria-label="Filter by API key">
          <option value="">{zh ? "全部密钥" : "All keys"}</option>
          {keys.map((key) => <option key={key.api_key_id} value={key.api_key_id}>{key.name || key.prefix || key.api_key_id}</option>)}
        </select>
      </div>
    </div>

    {loading ? <div className="border border-border-pg bg-bg-panel p-4 text-sm text-text-pg-muted rounded-xl">{zh ? "加载中…" : "Loading…"}</div> : null}

    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label={zh ? "总 Tokens" : "Total tokens"} value={num(totalTokens)} detail={zh ? "输入 + 输出 + 缓存" : "Input + output + cache"} tone="emerald" />
      <MetricCard label={zh ? "输入 Tokens" : "Input tokens"} value={num(totals.input_tokens)} detail={`${totals.reasoning_tokens} ${zh ? "推理" : "reasoning"}`} tone="cyan" />
      <MetricCard label={zh ? "输出 Tokens" : "Output tokens"} value={num(totals.output_tokens)} detail={zh ? "模型生成" : "Model-generated"} tone="cyan" />
      <MetricCard label={zh ? "缓存 Tokens" : "Cache tokens"} value={num(totals.cache_tokens)} detail={zh ? "命中缓存输入" : "Cache-hit input"} tone="neutral" />
      <MetricCard label={zh ? "请求数" : "Requests"} value={num(totals.requests)} detail={`${totals.success} ${zh ? "成功" : "ok"} · ${totals.errors} ${zh ? "错误" : "errors"}`} tone="amber" />
      <MetricCard label={zh ? "消费" : "Spend"} value={money(totals.cost_usd)} detail={zh ? "按零售价计费" : "At retail pricing"} tone="emerald" />
      <MetricCard label={zh ? "平均延迟" : "Avg latency"} value={`${num(Math.round(totals.avg_latency_ms))} ms`} detail={zh ? `峰值 ${totals.max_latency_ms} ms` : `Peak ${totals.max_latency_ms} ms`} tone="cyan" />
      <MetricCard label={zh ? "错误数" : "Errors"} value={num(totals.errors)} detail={zh ? "非 200 响应" : "Non-200 responses"} tone={totals.errors > 0 ? "red" : "neutral"} />
    </div>

    {!hasData && !loading && !usage?.unavailable ? <div className="mt-4"><EmptyState title={zh ? "该时间范围内暂无调用记录" : "No calls in this range"} description={zh ? "调整日期范围或先发起一次 API 调用。" : "Adjust the range or make an API call first."} /></div> : null}

    {hasData ? <div className="grid gap-4 xl:grid-cols-2">
      <ResearchCard><h3 className="font-semibold">{zh ? "Tokens 时间序列" : "Tokens over time"}</h3><div className="h-56"><ResponsiveContainer width="100%" height="100%"><AreaChart data={tokenSeries}><CartesianGrid stroke={grid} vertical={false} /><XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} /><YAxis stroke={text} tickLine={false} axisLine={false} width={44} /><Tooltip content={<ChartTooltip />} /><Area type="monotone" dataKey="input" name={zh ? "输入" : "Input"} stackId="1" stroke={positive} fill={positiveFill} strokeWidth={2} /><Area type="monotone" dataKey="output" name={zh ? "输出" : "Output"} stackId="1" stroke={white} fill={whiteFill} strokeWidth={2} /><Area type="monotone" dataKey="cache" name={zh ? "缓存" : "Cache"} stackId="1" stroke={warning} fill={warningFill} strokeWidth={2} /></AreaChart></ResponsiveContainer></div></ResearchCard>
      <ResearchCard><h3 className="font-semibold">{zh ? "请求与错误" : "Requests and errors"}</h3><div className="h-56"><ResponsiveContainer width="100%" height="100%"><BarChart data={requestSeries}><CartesianGrid stroke={grid} vertical={false} /><XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} /><YAxis stroke={text} tickLine={false} axisLine={false} width={36} /><Tooltip content={<ChartTooltip />} /><Bar dataKey="success" name={zh ? "成功" : "Success"} fill={positive} radius={[6, 6, 0, 0]} /><Bar dataKey="errors" name={zh ? "错误" : "Errors"} fill={negative} radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer></div></ResearchCard>
      <ResearchCard><h3 className="font-semibold">{zh ? "消费金额" : "Spend"}</h3><div className="h-56"><ResponsiveContainer width="100%" height="100%"><AreaChart data={costSeries}><CartesianGrid stroke={grid} vertical={false} /><XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} /><YAxis stroke={text} tickLine={false} axisLine={false} width={44} /><Tooltip content={<UsageTooltip prefix="$" />} /><Area type="monotone" dataKey="cost" name="USD" stroke={warning} fill={warningFill} strokeWidth={2} /></AreaChart></ResponsiveContainer></div></ResearchCard>
      <ResearchCard><h3 className="font-semibold">{zh ? "平均延迟" : "Average latency"}</h3><div className="h-56"><ResponsiveContainer width="100%" height="100%"><LineChart data={latencySeries}><CartesianGrid stroke={grid} vertical={false} /><XAxis dataKey="date" stroke={text} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} /><YAxis stroke={text} tickLine={false} axisLine={false} width={44} /><Tooltip content={<UsageTooltip />} /><Line type="monotone" dataKey="latency" name="ms" stroke={positive} strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div></ResearchCard>
    </div> : null}

    {hasData ? <ResearchCard>
      <h3 className="font-semibold">{zh ? "按模型拆解" : "By model"}</h3>
      <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="text-left text-xs uppercase tracking-[0.1em] text-text-pg-muted"><tr><th className="pb-2">{zh ? "模型" : "Model"}</th><th>{zh ? "请求数" : "Requests"}</th><th>{zh ? "输入" : "Input"}</th><th>{zh ? "输出" : "Output"}</th><th>{zh ? "缓存" : "Cache"}</th><th>{zh ? "平均延迟" : "Avg latency"}</th><th>{zh ? "消费" : "Spend"}</th></tr></thead><tbody>{byModel.map((row: GatewayUsageBreakdownRow) => <tr key={row.model} className="border-t border-border-pg"><td className="py-3 font-medium">{row.model}</td><td>{num(row.requests)}</td><td>{num(row.input_tokens)}</td><td>{num(row.output_tokens)}</td><td>{num(row.cache_tokens)}</td><td>{num(Math.round(row.avg_latency_ms))} ms</td><td className="font-mono text-xs">{money(row.cost_usd)}</td></tr>)}</tbody></table></div>
    </ResearchCard> : null}

    {hasData && byKey.length ? <ResearchCard>
      <h3 className="font-semibold">{zh ? "按密钥拆解" : "By API key"}</h3>
      <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="text-left text-xs uppercase tracking-[0.1em] text-text-pg-muted"><tr><th className="pb-2">{zh ? "密钥" : "Key"}</th><th>{zh ? "请求数" : "Requests"}</th><th>{zh ? "输入" : "Input"}</th><th>{zh ? "输出" : "Output"}</th><th>{zh ? "缓存" : "Cache"}</th><th>{zh ? "平均延迟" : "Avg latency"}</th><th>{zh ? "消费" : "Spend"}</th></tr></thead><tbody>{byKey.map((row: GatewayUsageBreakdownRow) => <tr key={row.api_key_id} className="border-t border-border-pg"><td className="py-3"><div className="font-medium">{row.name}</div><div className="font-mono text-xs text-text-pg-muted">{row.prefix}…</div></td><td>{num(row.requests)}</td><td>{num(row.input_tokens)}</td><td>{num(row.output_tokens)}</td><td>{num(row.cache_tokens)}</td><td>{num(Math.round(row.avg_latency_ms))} ms</td><td className="font-mono text-xs">{money(row.cost_usd)}</td></tr>)}</tbody></table></div>
    </ResearchCard> : null}
  </div>;
}
