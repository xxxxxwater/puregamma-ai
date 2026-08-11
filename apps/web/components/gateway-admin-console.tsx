"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Activity, Check, Power, RefreshCw, Save } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip } from "@/components/charts";
import { Badge, StatusDot } from "@/components/puregamma";
import {
  approveGatewayPrice,
  getGatewayAdminAccounts,
  getGatewayAdminProviders,
  getGatewayAdminUsage,
  getGatewayMetrics,
  getGatewayPendingPrices,
  getGatewayPricingPolicy,
  healthcheckGatewayProviders,
  setGatewayProviderEnabled,
  syncGatewayProviders,
  updateGatewayAccount,
  updateGatewayMarkup,
  type GatewayAdminAccount,
  type GatewayAdminProvider,
  type GatewayMetrics,
  type GatewayPriceRevision,
  type GatewayUsage,
  type GatewayUsageBucket,
} from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const money = (value: string) => `$${Number(value || 0).toFixed(4)}`;
const num = (value: number) => value.toLocaleString();

type AccountEdit = { status: "active" | "suspended"; monthlyLimit: string };

function providerTone(status: string): "emerald" | "red" | "amber" {
  return status === "healthy" ? "emerald" : status === "unhealthy" ? "red" : "amber";
}

// DeepSeek console design tokens (--dsw-*) — deepseek blue primary, bluish
// neutral greys, clean cards. Component-scoped, does not touch global themes.
const dsw = {
  deepseek500: "#3964fe",
  deepseek450: "#5686fe",
  deepseek400: "#679efe",
  deepseek300: "#b7c8fe",
  deepseek100: "#e4edfd",
  deepseek50: "#edf3fe",
  green500: "#22c55e",
  red500: "#f24242",
  amber500: "#f59e0b",
  ink: "#0f1115",
  inkMuted: "#7f8287",
  inkDim: "#a2a4a6",
  line: "rgba(15, 17, 21, 0.08)",
  cardBg: "#ffffff",
  panelBg: "#fafafa",
};

function UsageTooltip({ active, payload, label, prefix }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string; prefix?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ border: `1px solid ${dsw.line}`, background: dsw.cardBg, borderRadius: 10, padding: "8px 12px", fontSize: 12, boxShadow: "0 4px 12px rgba(0,0,0,0.06)" }}>
      <div style={{ color: dsw.inkMuted, marginBottom: 4 }}>{label}</div>
      {payload.map((item) => <div key={item.name} style={{ color: dsw.ink }}>{item.name}: {prefix || ""}{num(Number(item.value))}</div>)}
    </div>
  );
}

function DswCard({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section style={{ background: dsw.cardBg, border: `1px solid ${dsw.line}`, borderRadius: 12, padding: "16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: dsw.ink, margin: 0 }}>{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

type Preset = "24h" | "7d" | "30d" | "90d" | "custom";

function AdminUsageCharts({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [preset, setPreset] = useState<Preset>("7d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [usage, setUsage] = useState<GatewayUsage | null>(null);
  const [loading, setLoading] = useState(false);

  const now = useMemo(() => new Date(), []);
  const presets: { id: Preset; label: string; days: number }[] = [
    { id: "24h", label: zh ? "24 小时" : "24h", days: 1 },
    { id: "7d", label: zh ? "7 天" : "7d", days: 7 },
    { id: "30d", label: zh ? "30 天" : "30d", days: 30 },
    { id: "90d", label: zh ? "90 天" : "90d", days: 90 },
  ];

  const applyRange = async (start: Date, end: Date, granularity: "hour" | "day") => {
    setLoading(true);
    try {
      const result = await getGatewayAdminUsage(locale, {
        start: start.toISOString().slice(0, 19) + "+00:00",
        end: end.toISOString().slice(0, 19) + "+00:00",
        granularity,
      });
      setUsage(result);
    } finally {
      setLoading(false);
    }
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
  const totals = useMemo(
    () => usage?.totals ?? { requests: 0, success: 0, errors: 0, input_tokens: 0, output_tokens: 0, cache_tokens: 0, reasoning_tokens: 0, avg_latency_ms: 0, max_latency_ms: 0, cost_usd: "0" },
    [usage],
  );
  const hasData = buckets.some((bucket) => bucket.requests > 0);

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

  const axis = { stroke: dsw.inkMuted, fontSize: 11 };
  const gridLine = "rgba(15, 17, 21, 0.06)";
  const totalTokens = totals.input_tokens + totals.output_tokens + totals.cache_tokens;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 10 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: dsw.deepseek500 }}>{zh ? "用量分析" : "Usage analytics"}</div>
          <h2 style={{ margin: "4px 0 0", fontSize: 18, fontWeight: 600, color: dsw.ink }}>{zh ? "全站 Gateway 用量" : "Platform-wide Gateway usage"}</h2>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8 }}>
          {presets.map((item) => (
            <button key={item.id} type="button" disabled={loading} onClick={() => selectPreset(item.id)}
              style={{
                border: `1px solid ${preset === item.id ? dsw.deepseek500 : dsw.line}`,
                background: preset === item.id ? dsw.deepseek500 : dsw.cardBg,
                color: preset === item.id ? "#fff" : dsw.ink,
                padding: "6px 14px", fontSize: 13, borderRadius: 8, cursor: "pointer", fontWeight: preset === item.id ? 600 : 400,
              }}>
              {item.label}
            </button>
          ))}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
            <label style={{ fontSize: 12, color: dsw.inkMuted }}>{zh ? "起" : "From"}
              <input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)}
                style={{ display: "block", marginTop: 4, border: `1px solid ${dsw.line}`, background: dsw.cardBg, padding: "5px 8px", fontSize: 13, borderRadius: 8 }} />
            </label>
            <label style={{ fontSize: 12, color: dsw.inkMuted }}>{zh ? "止" : "To"}
              <input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)}
                style={{ display: "block", marginTop: 4, border: `1px solid ${dsw.line}`, background: dsw.cardBg, padding: "5px 8px", fontSize: 13, borderRadius: 8 }} />
            </label>
            <button type="button" disabled={loading || !customStart || !customEnd} onClick={applyCustom}
              style={{ border: `1px solid ${dsw.line}`, background: dsw.cardBg, color: dsw.ink, padding: "6px 14px", fontSize: 13, borderRadius: 8, cursor: "pointer" }}>
              {zh ? "应用" : "Apply"}
            </button>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
        {[
          { label: zh ? "总 Tokens" : "Total tokens", value: num(totalTokens) },
          { label: zh ? "请求数" : "Requests", value: num(totals.requests), detail: `${totals.success} ${zh ? "成功" : "ok"} · ${totals.errors} ${zh ? "错误" : "errors"}` },
          { label: zh ? "消费" : "Spend", value: money(totals.cost_usd) },
          { label: zh ? "平均延迟" : "Avg latency", value: `${num(Math.round(totals.avg_latency_ms))} ms`, detail: `${zh ? "峰值" : "Peak"} ${totals.max_latency_ms} ms` },
        ].map((item) => (
          <div key={item.label} style={{ background: dsw.cardBg, border: `1px solid ${dsw.line}`, borderRadius: 12, padding: "12px 14px" }}>
            <div style={{ fontSize: 12, color: dsw.inkMuted }}>{item.label}</div>
            <div style={{ fontSize: 20, fontWeight: 650, color: dsw.ink, marginTop: 4 }}>{item.value}</div>
            {item.detail ? <div style={{ fontSize: 11, color: dsw.inkDim, marginTop: 2 }}>{item.detail}</div> : null}
          </div>
        ))}
      </div>

      {loading ? <div style={{ border: `1px solid ${dsw.line}`, background: dsw.cardBg, padding: 16, fontSize: 13, color: dsw.inkMuted, borderRadius: 12 }}>{zh ? "加载中…" : "Loading…"}</div> : null}
      {!hasData && !loading ? <div style={{ border: `1px dashed ${dsw.line}`, background: dsw.panelBg, padding: "28px 16px", textAlign: "center", fontSize: 13, color: dsw.inkMuted, borderRadius: 12 }}>{zh ? "该时间范围内暂无调用记录。" : "No calls in this range."}</div> : null}

      {hasData ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 14 }}>
          <DswCard title={zh ? "Tokens 时间序列" : "Tokens over time"}>
            <div style={{ height: 220 }}><ResponsiveContainer width="100%" height="100%">
              <AreaChart data={tokenSeries}>
                <CartesianGrid stroke={gridLine} vertical={false} />
                <XAxis dataKey="date" stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                <YAxis stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} width={44} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="input" name={zh ? "输入" : "Input"} stackId="1" stroke={dsw.deepseek500} fill="rgba(57, 100, 254, 0.16)" strokeWidth={2} />
                <Area type="monotone" dataKey="output" name={zh ? "输出" : "Output"} stackId="1" stroke={dsw.deepseek400} fill="rgba(103, 158, 254, 0.14)" strokeWidth={2} />
                <Area type="monotone" dataKey="cache" name={zh ? "缓存" : "Cache"} stackId="1" stroke={dsw.deepseek300} fill="rgba(183, 200, 254, 0.18)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer></div>
          </DswCard>
          <DswCard title={zh ? "请求与错误" : "Requests and errors"}>
            <div style={{ height: 220 }}><ResponsiveContainer width="100%" height="100%">
              <BarChart data={requestSeries}>
                <CartesianGrid stroke={gridLine} vertical={false} />
                <XAxis dataKey="date" stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                <YAxis stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} width={36} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="success" name={zh ? "成功" : "Success"} fill={dsw.deepseek500} radius={[6, 6, 0, 0]} />
                <Bar dataKey="errors" name={zh ? "错误" : "Errors"} fill={dsw.red500} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer></div>
          </DswCard>
          <DswCard title={zh ? "消费金额" : "Spend"}>
            <div style={{ height: 220 }}><ResponsiveContainer width="100%" height="100%">
              <AreaChart data={costSeries}>
                <CartesianGrid stroke={gridLine} vertical={false} />
                <XAxis dataKey="date" stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                <YAxis stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} width={44} />
                <Tooltip content={<UsageTooltip prefix="$" />} />
                <Area type="monotone" dataKey="cost" name="USD" stroke={dsw.deepseek500} fill="rgba(57, 100, 254, 0.16)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer></div>
          </DswCard>
          <DswCard title={zh ? "平均延迟" : "Average latency"}>
            <div style={{ height: 220 }}><ResponsiveContainer width="100%" height="100%">
              <LineChart data={latencySeries}>
                <CartesianGrid stroke={gridLine} vertical={false} />
                <XAxis dataKey="date" stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                <YAxis stroke={axis.stroke} fontSize={axis.fontSize} tickLine={false} axisLine={false} width={44} />
                <Tooltip content={<UsageTooltip />} />
                <Line type="monotone" dataKey="latency" name="ms" stroke={dsw.deepseek500} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer></div>
          </DswCard>
        </div>
      ) : null}
    </div>
  );
}

export function GatewayAdminConsole({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [providers, setProviders] = useState<GatewayAdminProvider[]>([]);
  const [revisions, setRevisions] = useState<GatewayPriceRevision[]>([]);
  const [accounts, setAccounts] = useState<GatewayAdminAccount[]>([]);
  const [accountEdits, setAccountEdits] = useState<Record<string, AccountEdit>>({});
  const [metrics, setMetrics] = useState<GatewayMetrics | null>(null);
  const [markup, setMarkup] = useState("3000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [providerData, priceData, metricData, policyData, accountData] = await Promise.all([
        getGatewayAdminProviders(),
        getGatewayPendingPrices(),
        getGatewayMetrics(),
        getGatewayPricingPolicy(),
        getGatewayAdminAccounts(),
      ]);
      setProviders(providerData.providers);
      setRevisions(priceData.revisions);
      setMetrics(metricData);
      setMarkup(String(policyData.policy.markup_bps));
      setAccounts(accountData.accounts);
      setAccountEdits(Object.fromEntries(accountData.accounts.map((account) => [account.user_id, {
        status: account.account_status,
        monthlyLimit: account.monthly_spend_limit_usd,
      }])));
    } catch {
      setError(zh ? "无法读取 Gateway 管理数据。请确认当前账户为管理员。" : "Unable to load Gateway administration data. Confirm that the current account is an administrator.");
    }
  }, [zh]);

  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<void>, success: string) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load();
      setNotice(success);
    } catch {
      setError(zh ? "操作失败。请刷新后重试。" : "The operation failed. Refresh and try again.");
    } finally {
      setBusy(false);
    }
  };

  const sync = () => run(async () => { await syncGatewayProviders(); }, zh ? "已同步；所有价格变更仍需逐条确认。" : "Synchronized. Every price change still requires explicit approval.");
  const healthcheck = () => run(async () => { await healthcheckGatewayProviders(); }, zh ? "Provider 健康检查已完成。" : "Provider health checks completed.");
  const toggleProvider = (provider: GatewayAdminProvider) => run(
    async () => { await setGatewayProviderEnabled(provider.name, !provider.enabled); },
    provider.enabled ? (zh ? "Provider 已停用。" : "Provider disabled.") : (zh ? "Provider 已启用。" : "Provider enabled."),
  );
  const approve = (id: string) => run(async () => { await approveGatewayPrice(id); }, zh ? "价格已确认并立即生效。" : "Price approved and effective immediately.");

  const saveMarkup = () => {
    const parsed = Number(markup);
    if (!Number.isInteger(parsed) || parsed < 0 || parsed > 100000) {
      setError(zh ? "Markup 必须为 0–100000 个基点。" : "Markup must be 0–100000 basis points.");
      return;
    }
    return run(async () => { await updateGatewayMarkup(parsed); }, zh ? "默认 Markup 已更新。" : "Default markup updated.");
  };

  const saveAccount = (account: GatewayAdminAccount) => {
    const edit = accountEdits[account.user_id];
    const monthlyLimit = Number(edit?.monthlyLimit);
    if (!edit || !Number.isFinite(monthlyLimit) || monthlyLimit < 0 || monthlyLimit > 1_000_000) {
      setError(zh ? "月度限额必须为 0–1,000,000 USD；0 表示不设上限。" : "Monthly limit must be between 0 and 1,000,000 USD; 0 means unlimited.");
      return;
    }
    return run(
      async () => { await updateGatewayAccount(account.user_id, { status: edit.status, monthly_spend_limit_usd: monthlyLimit }); },
      zh ? "用户 Gateway 限额已更新。" : "User Gateway guardrail updated.",
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: dsw.cardBg, border: `1px solid ${dsw.line}`, borderRadius: 12, padding: "16px 18px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: dsw.deepseek500 }}>PureGamma API</div>
            <h2 style={{ margin: "4px 0 0", fontSize: 18, fontWeight: 600, color: dsw.ink }}>{zh ? "Provider、定价与用户计费管理" : "Provider, pricing, and account management"}</h2>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: dsw.inkMuted }}>{zh ? "同步只创建待审核版本；确认后才会对用户生效。" : "Sync creates pending revisions only; approval is required before customers can use them."}</p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="button" disabled={busy} onClick={() => void healthcheck()} style={{ display: "inline-flex", alignItems: "center", gap: 6, border: `1px solid ${dsw.line}`, background: dsw.cardBg, color: dsw.ink, padding: "8px 14px", fontSize: 13, borderRadius: 8, cursor: "pointer", opacity: busy ? 0.5 : 1 }}><Activity className="h-4 w-4" />{zh ? "健康检查" : "Health check"}</button>
            <button type="button" disabled={busy} onClick={() => void sync()} style={{ display: "inline-flex", alignItems: "center", gap: 6, border: "none", background: dsw.deepseek500, color: "#fff", padding: "8px 14px", fontSize: 13, fontWeight: 600, borderRadius: 8, cursor: "pointer", opacity: busy ? 0.5 : 1 }}><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />{zh ? "立即同步" : "Sync now"}</button>
          </div>
        </div>
        {error ? <p style={{ margin: "12px 0 0", fontSize: 13, color: dsw.red500 }}>{error}</p> : null}
        {notice ? <p style={{ margin: "12px 0 0", fontSize: 13, color: dsw.green500 }}>{notice}</p> : null}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginTop: 14 }}>
          <Metric label={zh ? "收入" : "Revenue"} value={money(metrics?.revenue_usd || "0")} />
          <Metric label={zh ? "官方成本" : "Provider cost"} value={money(metrics?.provider_cost_usd || "0")} />
          <Metric label={zh ? "毛利" : "Gross profit"} value={money(metrics?.profit_usd || "0")} />
          <Metric label={zh ? "用户预付余额" : "Prepaid balance liability"} value={money(metrics?.prepaid_liability_usd || "0")} />
          <Metric label={zh ? "成功及失败请求" : "Requests"} value={String(metrics?.requests || 0)} />
        </div>
      </div>

      <AdminUsageCharts locale={locale} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 14 }}>
        <DswCard title={zh ? "Provider 状态" : "Provider status"}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {providers.map((provider) => <div key={provider.id} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10, border: `1px solid ${dsw.line}`, background: dsw.panelBg, padding: "10px 12px", fontSize: 13, borderRadius: 10 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 500, color: dsw.ink }}>{provider.display_name}</div>
                <div style={{ marginTop: 2, fontSize: 12, color: dsw.inkMuted }}>{provider.models} {zh ? "个模型" : "models"} · {provider.last_error || "—"}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Badge tone={providerTone(provider.health_status)}><StatusDot tone={providerTone(provider.health_status)} /> {provider.health_status}</Badge>
                <button type="button" disabled={busy} onClick={() => void toggleProvider(provider)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: `1px solid ${dsw.line}`, background: dsw.cardBg, color: dsw.ink, padding: "4px 10px", fontSize: 12, borderRadius: 8, cursor: "pointer", opacity: busy ? 0.5 : 1 }}><Power className="h-3 w-3" />{provider.enabled ? (zh ? "停用" : "Disable") : (zh ? "启用" : "Enable")}</button>
              </div>
            </div>)}
            {!providers.length ? <p style={{ fontSize: 13, color: dsw.inkMuted }}>{zh ? "尚未初始化 Provider。" : "Providers are not initialized yet."}</p> : null}
          </div>
        </DswCard>

        <DswCard title={zh ? "默认 Markup" : "Default markup"}>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={markup} onChange={(event) => setMarkup(event.target.value)} inputMode="numeric" style={{ minWidth: 0, flex: 1, border: `1px solid ${dsw.line}`, background: dsw.panelBg, color: dsw.ink, padding: "8px 12px", fontSize: 13, borderRadius: 8 }} aria-label="Markup basis points" />
            <button type="button" onClick={() => void saveMarkup()} disabled={busy} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: `1px solid ${dsw.line}`, background: dsw.cardBg, color: dsw.ink, padding: "8px 12px", fontSize: 13, borderRadius: 8, cursor: "pointer", opacity: busy ? 0.5 : 1 }}><Save className="h-4 w-4" />{zh ? "保存" : "Save"}</button>
          </div>
          <p style={{ margin: "8px 0 0", fontSize: 12, color: dsw.inkMuted }}>3000 bp = 30%. {zh ? "保存后，会基于官方价格重新计算所有已激活模型。" : "Saving recalculates every active model from official prices."}</p>
          <p style={{ margin: "12px 0 0", fontSize: 12, color: dsw.inkMuted }}>{zh ? "此设置不会修改 Provider 的官方价格，也不会变更用户 Stripe 订阅。" : "This does not change Provider official pricing or a user's Stripe subscription."}</p>
        </DswCard>
      </div>

      <DswCard title={zh ? "待确认官方价格" : "Pending official prices"}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {revisions.map((revision) => <div key={revision.id} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10, border: `1px solid ${dsw.amber500}55`, background: dsw.panelBg, padding: "10px 12px", fontSize: 13, borderRadius: 10 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: "monospace", fontSize: 12, color: dsw.ink }}>{revision.model_id}</div>
              <div style={{ marginTop: 4, fontSize: 12, color: dsw.inkMuted }}>{revision.source_reference || revision.source_type} · {new Date(revision.synced_at).toLocaleString(locale)}</div>
              <div style={{ marginTop: 4, maxWidth: 720, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12, color: dsw.inkMuted }}>official: {JSON.stringify(revision.official_prices)} → final: {JSON.stringify(revision.final_prices)}</div>
            </div>
            <button type="button" disabled={busy} onClick={() => void approve(revision.id)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: `1px solid ${dsw.green500}`, background: dsw.cardBg, color: dsw.green500, padding: "8px 14px", fontSize: 13, borderRadius: 8, cursor: "pointer", opacity: busy ? 0.5 : 1 }}><Check className="h-4 w-4" />{zh ? "确认生效" : "Approve"}</button>
          </div>)}
          {!revisions.length ? <p style={{ fontSize: 13, color: dsw.inkMuted }}>{zh ? "没有待确认的价格变更。" : "No price changes await approval."}</p> : null}
        </div>
      </DswCard>

      <DswCard title={zh ? "用户访问与消费限额" : "User access and spending limits"}>
        <p style={{ margin: "0 0 12px", fontSize: 12, color: dsw.inkMuted }}>{zh ? "暂停会立即阻断该用户的 Gateway 请求；0 USD 表示月度不限额。预付余额独立于 PureGamma 订阅和 Credits，仅通过已验证的 Stripe 回调入账。" : "Suspending immediately blocks Gateway requests. A monthly limit of 0 USD means unlimited. Prepaid balance is independent from PureGamma subscriptions and Credits, and is credited only by verified Stripe webhooks."}</p>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", minWidth: 960, fontSize: 13, borderCollapse: "collapse" }}>
            <thead><tr style={{ textAlign: "left", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em", color: dsw.inkMuted }}><th style={{ paddingBottom: 8 }}>{zh ? "用户" : "User"}</th><th>{zh ? "套餐" : "Plan"}</th><th>{zh ? "状态" : "Status"}</th><th>{zh ? "API 余额" : "API balance"}</th><th>{zh ? "本月 / 累计" : "Month / lifetime"}</th><th>{zh ? "活跃密钥" : "Active keys"}</th><th>{zh ? "月度限额（USD）" : "Monthly limit (USD)"}</th><th /></tr></thead>
            <tbody>{accounts.map((account) => {
              const edit = accountEdits[account.user_id] || { status: account.account_status, monthlyLimit: account.monthly_spend_limit_usd };
              return <tr key={account.user_id} style={{ borderTop: `1px solid ${dsw.line}` }}>
                <td style={{ padding: "10px 0", verticalAlign: "middle" }}><div style={{ fontWeight: 500, color: dsw.ink }}>{account.name || "—"}</div><div style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12, color: dsw.inkMuted }}>{account.email}</div></td>
                <td><Badge tone="neutral">{account.plan}</Badge></td>
                <td><select value={edit.status} onChange={(event) => setAccountEdits((current) => ({ ...current, [account.user_id]: { ...edit, status: event.target.value as AccountEdit["status"] } }))} style={{ border: `1px solid ${dsw.line}`, background: dsw.panelBg, color: dsw.ink, padding: "4px 8px", fontSize: 12, borderRadius: 8 }}><option value="active">{zh ? "启用" : "Active"}</option><option value="suspended">{zh ? "暂停" : "Suspended"}</option></select></td>
                <td style={{ fontFamily: "monospace", fontSize: 12, color: dsw.ink }}>{money(account.wallet_balance_usd)}</td>
                <td style={{ fontSize: 12 }}><div>{money(account.current_month_spend_usd)}</div><div style={{ color: dsw.inkMuted }}>{money(account.lifetime_spend_usd)}</div></td>
                <td>{account.active_key_count} / 10</td>
                <td><input value={edit.monthlyLimit} onChange={(event) => setAccountEdits((current) => ({ ...current, [account.user_id]: { ...edit, monthlyLimit: event.target.value } }))} inputMode="decimal" style={{ width: 112, border: `1px solid ${dsw.line}`, background: dsw.panelBg, color: dsw.ink, padding: "4px 8px", fontSize: 13, borderRadius: 8 }} aria-label={`${account.email} monthly spend limit`} /></td>
                <td><button type="button" disabled={busy} onClick={() => void saveAccount(account)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: `1px solid ${dsw.line}`, background: dsw.cardBg, color: dsw.ink, padding: "4px 10px", fontSize: 12, borderRadius: 8, cursor: "pointer", opacity: busy ? 0.5 : 1 }}><Save className="h-3 w-3" />{zh ? "保存" : "Save"}</button></td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        {!accounts.length ? <p style={{ marginTop: 10, fontSize: 13, color: dsw.inkMuted }}>{zh ? "没有可管理的用户。" : "There are no users to manage."}</p> : null}
      </DswCard>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: dsw.panelBg, border: `1px solid ${dsw.line}`, borderRadius: 10, padding: "10px 12px" }}>
      <div style={{ fontSize: 12, color: dsw.inkMuted }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 650, color: dsw.ink, marginTop: 3 }}>{value}</div>
    </div>
  );
}
