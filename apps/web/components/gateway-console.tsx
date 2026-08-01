"use client";

import { useState } from "react";
import { Copy, CreditCard, KeyRound, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import { Badge, EmptyState, MetricCard, ResearchCard } from "@/components/puregamma";
import { UsagePanel } from "@/components/usage-panel";
import { changeGatewayKeyStatus, createGatewayKey, createGatewayTopup, rotateGatewayKey, type GatewayDashboard, type GatewayKey, type GatewayRequest, type GatewayUsage } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

type Props = { locale: Locale; dashboard: GatewayDashboard; initialKeys: GatewayKey[]; initialRequests: GatewayRequest[]; initialUsage: GatewayUsage };

const money = (value: string) => `$${Number(value || 0).toFixed(4)}`;

export function GatewayConsole({ locale, dashboard, initialKeys, initialRequests, initialUsage }: Props) {
  const zh = locale === "zh";
  const [keys, setKeys] = useState(initialKeys);
  const [oneTimeKey, setOneTimeKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [topupAmount, setTopupAmount] = useState(dashboard.wallet.topup_min_usd);
  const [topupBusy, setTopupBusy] = useState(false);
  const [message, setMessage] = useState("");

  const copy = async (value: string) => {
    await navigator.clipboard.writeText(value);
    setMessage(zh ? "已复制。请立即保存，此密钥不会再次显示。" : "Copied. Save it now; this key will not be shown again.");
  };
  const create = async () => {
    setBusy(true); setMessage("");
    try {
      const created = await createGatewayKey(zh ? "默认密钥" : "Default key");
      setKeys((current) => [created.api_key, ...current]);
      setOneTimeKey(created.key);
    } catch {
      setMessage(zh ? "无法创建密钥。每个账户最多可保留 10 个未撤销密钥。" : "Could not create a key. Each account can keep up to 10 non-revoked keys.");
    } finally { setBusy(false); }
  };
  const topup = async () => {
    setTopupBusy(true); setMessage("");
    try {
      const checkout = await createGatewayTopup(topupAmount, locale);
      window.location.assign(checkout.checkout_url);
    } catch {
      setMessage(zh ? `无法开始充值。请输入 $${dashboard.wallet.topup_min_usd}–$${dashboard.wallet.topup_max_usd}（最多两位小数）。` : `Could not start the top-up. Enter $${dashboard.wallet.topup_min_usd}–$${dashboard.wallet.topup_max_usd} with at most two decimals.`);
    } finally { setTopupBusy(false); }
  };
  const update = async (key: GatewayKey, action: "active" | "paused" | "revoked" | "rotate") => {
    setBusy(true); setMessage("");
    try {
      if (action === "rotate") {
        const replacement = await rotateGatewayKey(key.id);
        setKeys((current) => [replacement.api_key, ...current.map((item) => item.id === key.id ? { ...item, status: "revoked" as const } : item)]);
        setOneTimeKey(replacement.key);
      } else {
        await changeGatewayKeyStatus(key.id, action);
        setKeys((current) => current.map((item) => item.id === key.id ? { ...item, status: action } : item));
      }
    } catch {
      setMessage(zh ? "操作失败，请刷新后重试。" : "The operation failed. Refresh and try again.");
    } finally { setBusy(false); }
  };

  return <div className="space-y-5">
    {dashboard.unavailable ? <div className="border border-status-warning bg-bg-panel p-4 text-sm text-text-pg-muted">{zh ? "Gateway 数据暂不可用。请确认网关已启用并使用已登录账户访问。" : "Gateway data is unavailable. Confirm that the gateway is enabled and you are signed in."}</div> : null}
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label={zh ? "API 可用余额" : "API balance"} value={money(dashboard.wallet.available_balance_usd)} detail={zh ? "独立预付 USD，不影响 PureGamma 订阅" : "Separate prepaid USD; does not affect PureGamma subscriptions"} tone="emerald" />
      <MetricCard label={zh ? "今日消费" : "Today"} value={money(dashboard.spend_usd.today)} detail={zh ? "按确认后的零售价计费" : "At approved retail pricing"} tone="cyan" />
      <MetricCard label={zh ? "本月消费" : "This month"} value={money(dashboard.spend_usd.month)} detail={`${dashboard.subscription.plan || "—"} plan`} tone="amber" />
      <MetricCard label={zh ? "累计消费" : "Lifetime"} value={money(dashboard.spend_usd.lifetime)} detail={`${keys.length} / 10 ${zh ? "个密钥" : "keys"}`} tone="cyan" />
      <MetricCard label={zh ? "月度限额" : "Monthly limit"} value={Number(dashboard.account.monthly_spend_limit_usd) > 0 ? money(dashboard.account.monthly_spend_limit_usd) : (zh ? "不限额" : "Unlimited")} detail={dashboard.account.status === "active" ? (zh ? "Gateway 已启用" : "Gateway active") : (zh ? "Gateway 已暂停" : "Gateway suspended")} tone="neutral" />
    </div>

    <ResearchCard>
      <UsagePanel locale={locale} initialUsage={initialUsage} />
    </ResearchCard>

    <ResearchCard>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-eyebrow uppercase text-text-pg-muted">Gateway prepaid wallet</div>
          <h2 className="mt-1 font-semibold">{zh ? "充值 API 余额" : "Add API balance"}</h2>
          <p className="mt-1 max-w-2xl text-sm text-text-pg-muted">{zh ? "输入任意美元金额，Stripe 付款确认的金额将 1:1 计入中转站余额。PureGamma 订阅、套餐和 Credits 不会被修改。" : "Enter any USD amount. The amount confirmed by Stripe is credited 1:1 to this Gateway wallet; PureGamma subscriptions, plans, and Credits are untouched."}</p>
        </div>
        <div className="flex min-w-[250px] flex-col gap-2 sm:flex-row sm:items-end">
          <label className="text-sm"><span className="mb-1 block text-xs text-text-pg-muted">USD · {zh ? `范围 $${dashboard.wallet.topup_min_usd}–$${dashboard.wallet.topup_max_usd}` : `$${dashboard.wallet.topup_min_usd}–$${dashboard.wallet.topup_max_usd}`}</span><input value={topupAmount} onChange={(event) => setTopupAmount(event.target.value)} inputMode="decimal" type="number" min={dashboard.wallet.topup_min_usd} max={dashboard.wallet.topup_max_usd} step="0.01" className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" aria-label="Gateway top-up amount in USD" /></label>
          <button type="button" disabled={topupBusy || dashboard.unavailable} onClick={() => void topup()} className="inline-flex h-10 items-center justify-center gap-2 border border-border-pg bg-text-pg px-3 text-sm font-semibold text-bg-panel disabled:opacity-50"><CreditCard className="h-4 w-4" />{zh ? "前往 Stripe 付款" : "Pay with Stripe"}</button>
        </div>
      </div>
      <p className="mt-3 text-xs text-text-pg-muted">{zh ? "余额仅由已验证的 Stripe Webhook 入账；支付成功页面不会直接改变余额。" : "Only a verified Stripe webhook credits the balance; the payment success page never does."}</p>
    </ResearchCard>

    <ResearchCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="text-eyebrow uppercase text-text-pg-muted">OpenAI compatible</div><h2 className="mt-1 font-semibold">{zh ? "API 密钥" : "API keys"}</h2><p className="mt-1 text-sm text-text-pg-muted">{zh ? "Base URL: https://api.puregamma.ai/v1" : "Base URL: https://api.puregamma.ai/v1"}</p></div>
        <button type="button" onClick={create} disabled={busy || keys.filter((key) => key.status !== "revoked").length >= 10} className="inline-flex items-center gap-2 border border-border-pg bg-text-pg px-3 py-2 text-sm font-semibold text-bg-panel disabled:opacity-50"><KeyRound className="h-4 w-4" />{zh ? "创建密钥" : "Create key"}</button>
      </div>
      {oneTimeKey ? <div className="mt-4 border border-status-positive bg-bg-panel-muted p-3"><div className="text-xs font-semibold uppercase tracking-wider text-status-positive">{zh ? "仅显示一次" : "Shown once"}</div><div className="mt-2 flex flex-wrap items-center gap-2"><code className="max-w-full overflow-x-auto border border-border-pg px-2 py-1 text-xs">{oneTimeKey}</code><button type="button" onClick={() => void copy(oneTimeKey)} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs"><Copy className="h-3 w-3" />{zh ? "复制" : "Copy"}</button></div></div> : null}
      {message ? <p className="mt-3 text-sm text-text-pg-muted">{message}</p> : null}
      <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead className="text-left text-xs uppercase tracking-[0.1em] text-text-pg-muted"><tr><th className="pb-2">{zh ? "名称" : "Name"}</th><th>{zh ? "前缀" : "Prefix"}</th><th>{zh ? "状态" : "Status"}</th><th>RPM</th><th>{zh ? "最后调用" : "Last used"}</th><th /></tr></thead><tbody>{keys.map((key) => <tr key={key.id} className="border-t border-border-pg"><td className="py-3 font-medium">{key.name}</td><td className="font-mono text-xs">{key.prefix}…{key.last_four}</td><td><Badge tone={key.status === "active" ? "emerald" : key.status === "paused" ? "amber" : "neutral"}>{key.status}</Badge></td><td>{key.rate_limit_rpm}</td><td className="text-xs text-text-pg-muted">{key.last_used_at ? new Date(key.last_used_at).toLocaleString(locale) : "—"}</td><td><div className="flex justify-end gap-1">{key.status === "active" ? <button aria-label="Pause" type="button" disabled={busy} onClick={() => void update(key, "paused")} className="border border-border-pg p-2"><Pause className="h-3 w-3" /></button> : key.status === "paused" ? <button aria-label="Resume" type="button" disabled={busy} onClick={() => void update(key, "active")} className="border border-border-pg p-2"><Play className="h-3 w-3" /></button> : null}{key.status !== "revoked" ? <><button aria-label="Rotate" type="button" disabled={busy} onClick={() => void update(key, "rotate")} className="border border-border-pg p-2"><RefreshCw className="h-3 w-3" /></button><button aria-label="Revoke" type="button" disabled={busy} onClick={() => void update(key, "revoked")} className="border border-border-pg p-2 text-status-negative"><Trash2 className="h-3 w-3" /></button></> : null}</div></td></tr>)}</tbody></table></div>
      {!keys.length ? <div className="mt-4"><EmptyState title={zh ? "尚未创建 API 密钥" : "No API keys yet"} description={zh ? "创建密钥后即可使用 OpenAI SDK。" : "Create a key to use the OpenAI SDK."} /></div> : null}
    </ResearchCard>

    <div className="grid gap-4 xl:grid-cols-3">
      <ResearchCard><h2 className="font-semibold">{zh ? "模型使用" : "Model usage"}</h2>{dashboard.models.length ? <div className="mt-3 space-y-2">{dashboard.models.map((model) => <div key={model.model} className="flex items-center justify-between border-t border-border-pg py-2 text-sm"><div><div className="font-medium">{model.model}</div><div className="text-xs text-text-pg-muted">{model.requests} {zh ? "次请求" : "requests"} · {model.input_tokens + model.output_tokens} tokens</div></div><span>{money(model.cost_usd)}</span></div>)}</div> : <div className="mt-3"><EmptyState title={zh ? "暂无模型用量" : "No model usage"} description={zh ? "完成调用后会在这里汇总。" : "Completed calls will appear here."} /></div>}</ResearchCard>
      <ResearchCard><h2 className="font-semibold">{zh ? "最近请求" : "Recent requests"}</h2>{initialRequests.length ? <div className="mt-3 space-y-2">{initialRequests.map((item) => <div key={item.id} className="flex items-center justify-between gap-3 border-t border-border-pg py-2 text-sm"><div className="min-w-0"><div className="truncate font-medium">{item.model}</div><div className="text-xs text-text-pg-muted">{item.input_tokens} in / {item.output_tokens} out · {item.latency_ms}ms</div></div><div className="text-right"><Badge tone={item.status === "success" ? "emerald" : "red"}>{item.http_status}</Badge><div className="mt-1 text-xs">{money(item.cost_usd)}</div></div></div>)}</div> : <div className="mt-3"><EmptyState title={zh ? "暂无调用记录" : "No requests yet"} description={zh ? "请求历史不保存提示词内容。" : "Request history never stores prompt contents."} /></div>}</ResearchCard>
      <ResearchCard><h2 className="font-semibold">{zh ? "余额记录" : "Wallet activity"}</h2>{dashboard.wallet_ledger.length ? <div className="mt-3 space-y-2">{dashboard.wallet_ledger.map((entry) => <div key={entry.id} className="flex items-center justify-between gap-3 border-t border-border-pg py-2 text-sm"><div><div className="font-medium">{entry.entry_type === "topup" ? (zh ? "Stripe 充值" : "Stripe top-up") : (zh ? "API 调用" : "API usage")}</div><div className="text-xs text-text-pg-muted">{new Date(entry.created_at).toLocaleString(locale)}</div></div><div className="text-right"><div className={Number(entry.amount_usd) >= 0 ? "text-status-positive" : "text-text-pg"}>{Number(entry.amount_usd) >= 0 ? "+" : ""}{money(entry.amount_usd)}</div><div className="text-xs text-text-pg-muted">{zh ? "余额" : "Balance"} {money(entry.balance_after_usd)}</div></div></div>)}</div> : <div className="mt-3"><EmptyState title={zh ? "暂无充值或用量" : "No wallet activity"} description={zh ? "充值到账和 API 调用会显示在这里。" : "Confirmed top-ups and API usage will appear here."} /></div>}</ResearchCard>
    </div>
  </div>;
}
