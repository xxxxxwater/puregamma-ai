"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Check, Power, RefreshCw, Save } from "lucide-react";
import { Badge, ResearchCard, StatusDot } from "@/components/puregamma";
import {
  approveGatewayPrice,
  getGatewayAdminAccounts,
  getGatewayAdminProviders,
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
} from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const money = (value: string) => `$${Number(value || 0).toFixed(4)}`;

type AccountEdit = { status: "active" | "suspended"; monthlyLimit: string };

function providerTone(status: string): "emerald" | "red" | "amber" {
  return status === "healthy" ? "emerald" : status === "unhealthy" ? "red" : "amber";
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
    <div className="space-y-4">
      <ResearchCard>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-eyebrow uppercase text-text-pg-muted">PureGamma API</div>
            <h2 className="mt-1 font-semibold">{zh ? "Provider、定价与用户计费管理" : "Provider, pricing, and account management"}</h2>
            <p className="mt-1 text-sm text-text-pg-muted">{zh ? "同步只创建待审核版本；确认后才会对用户生效。" : "Sync creates pending revisions only; approval is required before customers can use them."}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={() => void healthcheck()} className="inline-flex items-center gap-2 border border-border-pg px-3 py-2 text-sm disabled:opacity-50"><Activity className="h-4 w-4" />{zh ? "健康检查" : "Health check"}</button>
            <button type="button" disabled={busy} onClick={() => void sync()} className="inline-flex items-center gap-2 border border-border-pg bg-text-pg px-3 py-2 text-sm font-semibold text-bg-panel disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />{zh ? "立即同步" : "Sync now"}</button>
          </div>
        </div>
        {error ? <p className="mt-3 text-sm text-status-negative">{error}</p> : null}
        {notice ? <p className="mt-3 text-sm text-status-positive">{notice}</p> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-5">
          <Metric label={zh ? "收入" : "Revenue"} value={money(metrics?.revenue_usd || "0")} />
          <Metric label={zh ? "官方成本" : "Provider cost"} value={money(metrics?.provider_cost_usd || "0")} />
          <Metric label={zh ? "毛利" : "Gross profit"} value={money(metrics?.profit_usd || "0")} />
          <Metric label={zh ? "用户预付余额" : "Prepaid balance liability"} value={money(metrics?.prepaid_liability_usd || "0")} />
          <Metric label={zh ? "成功及失败请求" : "Requests"} value={String(metrics?.requests || 0)} />
        </div>
      </ResearchCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <ResearchCard>
          <h3 className="text-sm font-semibold">{zh ? "Provider 状态" : "Provider status"}</h3>
          <div className="mt-3 space-y-2">
            {providers.map((provider) => <div key={provider.id} className="flex flex-wrap items-center justify-between gap-3 border border-border-pg bg-bg-panel-muted p-3 text-sm">
              <div className="min-w-0">
                <div className="font-medium">{provider.display_name}</div>
                <div className="mt-0.5 text-xs text-text-pg-muted">{provider.models} {zh ? "个模型" : "models"} · {provider.last_error || "—"}</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={providerTone(provider.health_status)}><StatusDot tone={providerTone(provider.health_status)} /> {provider.health_status}</Badge>
                <button type="button" disabled={busy} onClick={() => void toggleProvider(provider)} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs disabled:opacity-50"><Power className="h-3 w-3" />{provider.enabled ? (zh ? "停用" : "Disable") : (zh ? "启用" : "Enable")}</button>
              </div>
            </div>)}
            {!providers.length ? <p className="text-sm text-text-pg-muted">{zh ? "尚未初始化 Provider。" : "Providers are not initialized yet."}</p> : null}
          </div>
        </ResearchCard>

        <ResearchCard>
          <h3 className="text-sm font-semibold">{zh ? "默认 Markup" : "Default markup"}</h3>
          <div className="mt-3 flex gap-2">
            <input value={markup} onChange={(event) => setMarkup(event.target.value)} inputMode="numeric" className="min-w-0 flex-1 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" aria-label="Markup basis points" />
            <button type="button" onClick={() => void saveMarkup()} disabled={busy} className="inline-flex items-center gap-1 border border-border-pg px-3 py-2 text-sm disabled:opacity-50"><Save className="h-4 w-4" />{zh ? "保存" : "Save"}</button>
          </div>
          <p className="mt-2 text-xs text-text-pg-muted">3000 bp = 30%. {zh ? "保存后，会基于官方价格重新计算所有已激活模型。" : "Saving recalculates every active model from official prices."}</p>
          <p className="mt-4 text-xs text-text-pg-muted">{zh ? "此设置不会修改 Provider 的官方价格，也不会变更用户 Stripe 订阅。" : "This does not change Provider official pricing or a user's Stripe subscription."}</p>
        </ResearchCard>
      </div>

      <ResearchCard>
        <h3 className="text-sm font-semibold">{zh ? "待确认官方价格" : "Pending official prices"}</h3>
        <div className="mt-3 space-y-2">
          {revisions.map((revision) => <div key={revision.id} className="flex flex-wrap items-center justify-between gap-3 border border-status-warning/50 bg-bg-panel-muted p-3 text-sm">
            <div className="min-w-0">
              <div className="font-mono text-xs">{revision.model_id}</div>
              <div className="mt-1 text-xs text-text-pg-muted">{revision.source_reference || revision.source_type} · {new Date(revision.synced_at).toLocaleString(locale)}</div>
              <div className="mt-1 max-w-[720px] truncate text-xs text-text-pg-muted">official: {JSON.stringify(revision.official_prices)} → final: {JSON.stringify(revision.final_prices)}</div>
            </div>
            <button type="button" disabled={busy} onClick={() => void approve(revision.id)} className="inline-flex items-center gap-1 border border-status-positive px-3 py-2 text-sm text-status-positive disabled:opacity-50"><Check className="h-4 w-4" />{zh ? "确认生效" : "Approve"}</button>
          </div>)}
          {!revisions.length ? <p className="text-sm text-text-pg-muted">{zh ? "没有待确认的价格变更。" : "No price changes await approval."}</p> : null}
        </div>
      </ResearchCard>

      <ResearchCard>
        <div>
          <h3 className="text-sm font-semibold">{zh ? "用户访问与消费限额" : "User access and spending limits"}</h3>
          <p className="mt-1 text-xs text-text-pg-muted">{zh ? "暂停会立即阻断该用户的 Gateway 请求；0 USD 表示月度不限额。预付余额独立于 PureGamma 订阅和 Credits，仅通过已验证的 Stripe 回调入账。" : "Suspending immediately blocks Gateway requests. A monthly limit of 0 USD means unlimited. Prepaid balance is independent from PureGamma subscriptions and Credits, and is credited only by verified Stripe webhooks."}</p>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead className="text-left text-xs uppercase tracking-[0.1em] text-text-pg-muted"><tr><th className="pb-2">{zh ? "用户" : "User"}</th><th>{zh ? "套餐" : "Plan"}</th><th>{zh ? "状态" : "Status"}</th><th>{zh ? "API 余额" : "API balance"}</th><th>{zh ? "本月 / 累计" : "Month / lifetime"}</th><th>{zh ? "活跃密钥" : "Active keys"}</th><th>{zh ? "月度限额（USD）" : "Monthly limit (USD)"}</th><th /></tr></thead>
            <tbody>{accounts.map((account) => {
              const edit = accountEdits[account.user_id] || { status: account.account_status, monthlyLimit: account.monthly_spend_limit_usd };
              return <tr key={account.user_id} className="border-t border-border-pg align-middle"><td className="py-3"><div className="font-medium">{account.name || "—"}</div><div className="max-w-[220px] truncate text-xs text-text-pg-muted">{account.email}</div></td><td><Badge tone="neutral">{account.plan}</Badge></td><td><select value={edit.status} onChange={(event) => setAccountEdits((current) => ({ ...current, [account.user_id]: { ...edit, status: event.target.value as AccountEdit["status"] } }))} className="border border-border-pg bg-bg-panel-muted px-2 py-1 text-xs"><option value="active">{zh ? "启用" : "Active"}</option><option value="suspended">{zh ? "暂停" : "Suspended"}</option></select></td><td className="font-mono text-xs">{money(account.wallet_balance_usd)}</td><td className="text-xs"><div>{money(account.current_month_spend_usd)}</div><div className="text-text-pg-muted">{money(account.lifetime_spend_usd)}</div></td><td>{account.active_key_count} / 10</td><td><input value={edit.monthlyLimit} onChange={(event) => setAccountEdits((current) => ({ ...current, [account.user_id]: { ...edit, monthlyLimit: event.target.value } }))} inputMode="decimal" className="w-28 border border-border-pg bg-bg-panel-muted px-2 py-1 text-sm" aria-label={`${account.email} monthly spend limit`} /></td><td><button type="button" disabled={busy} onClick={() => void saveAccount(account)} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs disabled:opacity-50"><Save className="h-3 w-3" />{zh ? "保存" : "Save"}</button></td></tr>;
            })}</tbody>
          </table>
        </div>
        {!accounts.length ? <p className="mt-3 text-sm text-text-pg-muted">{zh ? "没有可管理的用户。" : "There are no users to manage."}</p> : null}
      </ResearchCard>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="border border-border-pg bg-bg-panel-muted p-3"><div className="text-xs text-text-pg-muted">{label}</div><div className="mt-1 font-semibold">{value}</div></div>;
}
