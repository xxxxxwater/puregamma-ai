"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Link2, Loader2, Play, RefreshCw, Trash2, Wallet } from "lucide-react";
import { AllocationChart, NavHistoryChart } from "@/components/charts";
import { AutopilotToggle, HoldingRow, ProviderCard } from "@/components/portfolio-panels";
import { Badge, ErrorState, LoadingSkeleton, ResearchCard, StatusDot } from "@/components/puregamma";
import { connectEvmWallet, connectHyperliquid, createEvmWalletChallenge, createPlaidLinkToken, disconnectPortfolioAccount, emptyPortfolioSnapshot, exchangePlaidToken, getMe, getPlaidInvestmentTransactions, getPortfolioAutopilot, getPortfolioSnapshot, getSkillCatalog, requestPlaidInvestmentRefresh, runPortfolioAutopilot, syncPortfolioAccount, updatePortfolioAutopilot, type PortfolioAutopilot, type PortfolioDataQuality, type PortfolioHolding, type PortfolioInvestmentTransaction, type PortfolioSnapshot, type SkillSummary } from "@/lib/api";
import { type Locale, withLocale } from "@/i18n/routing";

declare global { interface Window { Plaid?: { create: (config: Record<string, unknown>) => { open: () => void } }; ethereum?: { request: (payload: { method: string; params?: unknown[] }) => Promise<unknown> } } }

const empty: PortfolioSnapshot = emptyPortfolioSnapshot();
const emptyAutopilot: PortfolioAutopilot = { config: { enabled: false, cadence: "daily", auto_sync: true, risk_alerts: true, long_gamma_watch: true, delivery: "in_app", skill_refs: [] }, account_count: 0, findings: [], execution: "RESEARCH_ONLY", last_review: null };
const PLAID_LINK_TOKEN_KEY = "pg_plaid_link_token";
const PLAID_CONNECTION_MODE_KEY = "pg_plaid_connection_mode";
type PlaidConnectionMode = "plaid" | "ibkr";
type PortfolioQualityStatus = PortfolioDataQuality["status"];

function qualityStatusLabel(status: PortfolioQualityStatus, zh: boolean) {
  const labels: Record<string, { en: string; zh: string }> = {
    NO_ACCOUNTS: { en: "No accounts", zh: "未连接账户" },
    PENDING_SYNC: { en: "Pending sync", zh: "等待同步" },
    PARTIAL: { en: "Partial data", zh: "数据不完整" },
    STALE: { en: "Stale data", zh: "数据过期" },
    CURRENT: { en: "Current", zh: "数据新鲜" },
  };
  const label = labels[status] ?? { en: status || "Unknown", zh: status || "未知" };
  return zh ? label.zh : label.en;
}

function qualityStatusTone(status: PortfolioQualityStatus) {
  if (status === "CURRENT") return "emerald";
  if (status === "NO_ACCOUNTS") return "neutral";
  return "amber";
}

function connectionStatusLabel(status: string, zh: boolean) {
  const labels: Record<string, { en: string; zh: string }> = {
    CONNECTED: { en: "Connected", zh: "已连接" },
    STALE: { en: "Stale", zh: "数据过期" },
    PENDING_SYNC: { en: "Pending sync", zh: "等待同步" },
    PENDING_HISTORY: { en: "Preparing history", zh: "历史准备中" },
    PENDING_REFRESH: { en: "Refreshing", zh: "更新中" },
    ERROR: { en: "Error", zh: "同步错误" },
    DISCONNECTED: { en: "Disconnected", zh: "已断开" },
  };
  const label = labels[status.toUpperCase()];
  return label ? (zh ? label.zh : label.en) : status;
}

function connectionStatusTone(status: string) {
  const normalized = status.toUpperCase();
  if (normalized === "CONNECTED") return "text-status-positive";
  if (normalized === "ERROR" || normalized === "DISCONNECTED") return "text-status-negative";
  return "text-status-warning";
}

function qualityDetail(quality: PortfolioDataQuality | undefined, zh: boolean) {
  if (!quality) return zh ? "数据质量未知" : "Data quality unknown";
  if (quality.total_accounts === 0) return zh ? "连接只读账户后开始计算 NAV" : "Connect read-only accounts to compute NAV";
  const sourceLabel = quality.source_count === 1 ? "source" : "sources";
  return zh
    ? `已同步 ${quality.synced_accounts}/${quality.total_accounts} 个账户 · ${quality.source_count} 个来源`
    : `${quality.synced_accounts}/${quality.total_accounts} accounts synced · ${quality.source_count} ${sourceLabel}`;
}

function qualityWarning(quality: PortfolioDataQuality | undefined, zh: boolean) {
  if (!quality || quality.status === "CURRENT") return "";
  if (quality.status === "NO_ACCOUNTS") {
    return zh ? "尚未连接真实组合账户。当前不展示估算 NAV。" : "No real portfolio account is connected. Estimated NAV is not shown.";
  }
  if (quality.status === "PENDING_SYNC") {
    return zh ? "账户已连接，但还没有成功同步快照。请先同步账户。" : "Accounts are connected, but no snapshot has synced yet. Sync accounts first.";
  }
  const affected = [...quality.missing_accounts, ...quality.stale_accounts]
    .slice(0, 3)
    .map((account) => account.name)
    .join(", ");
  if (quality.status === "PARTIAL") {
    return zh
      ? `当前 NAV 只包含已同步账户。待同步：${affected || "部分账户"}。`
      : `Current NAV only includes synced accounts. Waiting on: ${affected || "some accounts"}.`;
  }
  return zh
    ? `至少一个账户快照已过期。请同步后再依赖 NAV：${affected || "部分账户"}。`
    : `At least one account snapshot is stale. Sync before relying on NAV: ${affected || "some accounts"}.`;
}

async function launchPlaidLink(linkToken: string, onSuccess: (publicToken: string, institutionName: string) => Promise<void>, onExit: () => void, receivedRedirectUri?: string, zh = false) {
  const blockedMessage = zh ? "Plaid Link 脚本被浏览器拦截，请关闭广告/隐私拦截插件或更换网络后重试。" : "Plaid Link was blocked by the browser. Disable ad/privacy blockers for this site or try another network, then retry.";
  const failedMessage = zh ? "Plaid Link 脚本加载失败，请检查网络连接后重试。" : "Plaid Link failed to load. Check your network connection and retry.";
  for (let attempt = 0; attempt < 2 && !window.Plaid; attempt += 1) {
    let script = document.querySelector<HTMLScriptElement>("script[data-plaid-link]");
    if (script?.dataset.plaidState === "error" || script?.dataset.plaidState === "blocked") { script.remove(); script = null; }
    if (!script) {
      script = document.createElement("script");
      script.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
      script.dataset.plaidLink = "true";
      script.dataset.plaidState = "loading";
      script.onload = () => { script!.dataset.plaidState = window.Plaid ? "ready" : "blocked"; };
      script.onerror = () => { script!.dataset.plaidState = "error"; };
      document.head.appendChild(script);
    }
    const deadline = Date.now() + 30_000;
    while (script.dataset.plaidState === "loading" && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 100));
    if (script.dataset.plaidState === "ready" && window.Plaid) break;
    const state = script.dataset.plaidState;
    script.remove();
    if (state === "blocked") throw new Error(blockedMessage);
    if (attempt === 1) throw new Error(failedMessage);
  }
  if (!window.Plaid) throw new Error(blockedMessage);
  window.Plaid.create({ token: linkToken, receivedRedirectUri, onSuccess: async (publicToken: string, metadata: { institution?: { name?: string } }) => onSuccess(publicToken, metadata.institution?.name || "Plaid Investments"), onExit }).open();
}

export function PortfolioConsole({ locale }: { locale: Locale }) {
  const router = useRouter();
  const zh = locale === "zh";
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot>(empty);
  const [snapshotLoading, setSnapshotLoading] = useState(true);
  const [snapshotError, setSnapshotError] = useState("");
  const [plaidTransactions, setPlaidTransactions] = useState<PortfolioInvestmentTransaction[]>([]);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [autopilot, setAutopilot] = useState<PortfolioAutopilot>(emptyAutopilot);
  const [autopilotSkills, setAutopilotSkills] = useState<SkillSummary[]>([]);
  const [range, setRange] = useState<"1D" | "1W" | "1M" | "ALL">("1M");
  const formatError = useCallback((reason: unknown): string => {
    const raw = (reason as Error)?.message || String(reason);
    try {
      const parsed = JSON.parse(raw) as { detail?: { code?: string; plan?: string; active_count?: number; max_portfolios?: number; message?: string } | string };
      const detail = parsed.detail;
      if (detail && typeof detail === "object") {
        if (detail.code === "PORTFOLIO_LIMIT_REACHED") {
          const plan = detail.plan ?? "Free";
          const max = detail.max_portfolios ?? 0;
          const used = detail.active_count ?? 0;
          return zh
            ? `当前 ${plan} 计划最多可连接 ${max} 个组合账户（已连接 ${used} 个）。${max === 0 ? "升级计划后即可连接 MetaMask 等账户。" : "请断开不用的账户，或升级计划。"}`
            : `Your ${plan} plan allows ${max} portfolio account(s) and ${used} are connected. ${max === 0 ? "Upgrade your plan to connect MetaMask and other accounts." : "Disconnect an unused account or upgrade your plan."}`;
        }
        if (detail.code === "PORTFOLIO_ACCESS_RESTRICTED") {
          return zh ? "订阅状态受限（续费失败或已取消），暂时无法连接组合账户。请检查账单状态。" : "Your subscription is restricted (payment issue or cancellation), so portfolio connections are temporarily unavailable. Review your billing status.";
        }
        if (detail.message) return String(detail.message);
      }
      if (typeof detail === "string") return detail;
    } catch { /* response was not JSON */ }
    return raw;
  }, [zh]);
  const loadSnapshot = useCallback(async () => {
    setSnapshotLoading(true);
    setSnapshotError("");
    try {
      setPortfolio(await getPortfolioSnapshot(locale));
    } catch (reason) {
      setSnapshotError(formatError(reason));
    } finally {
      setSnapshotLoading(false);
    }
  }, [locale, formatError]);
  useEffect(() => {
    void getMe().catch((reason: Error & { status?: number }) => {
      if (reason.status === 401) router.replace(`${withLocale(locale, "/login")}?returnTo=${encodeURIComponent(withLocale(locale, "/portfolio"))}`);
    });
    void loadSnapshot();
    void getPlaidInvestmentTransactions().then(({ transactions }) => setPlaidTransactions(transactions)).catch(() => undefined);
    void getPortfolioAutopilot().then(setAutopilot);
    void getSkillCatalog().then(({ skills }) => setAutopilotSkills(skills.filter((skill) => skill.allow_autopilot && skill.tool_allowlist.includes("get_account_snapshot"))));

    const params = new URLSearchParams(window.location.search);
    const oauthState = params.get("oauth_state_id");
    const storedLinkToken = window.sessionStorage.getItem(PLAID_LINK_TOKEN_KEY);
    const storedMode = window.sessionStorage.getItem(PLAID_CONNECTION_MODE_KEY) === "ibkr" ? "ibkr" : "plaid";
    if (oauthState && storedLinkToken) {
      setBusy(storedMode);
      void launchPlaidLink(storedLinkToken, async (publicToken, institutionName) => {
        setPortfolio(await exchangePlaidToken(publicToken, institutionName));
        window.sessionStorage.removeItem(PLAID_LINK_TOKEN_KEY);
        window.sessionStorage.removeItem(PLAID_CONNECTION_MODE_KEY);
        setBusy("");
        window.history.replaceState({}, "", window.location.pathname);
      }, () => setBusy(""), window.location.href, zh).catch((reason: Error) => {
        setError(formatError(reason));
        setBusy("");
      });
    }
  }, [locale, router, zh, loadSnapshot, formatError]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void getPortfolioSnapshot(locale).then((snapshot) => { setPortfolio(snapshot); setSnapshotError(""); }).catch(() => undefined);
        void getPlaidInvestmentTransactions().then(({ transactions }) => setPlaidTransactions(transactions)).catch(() => undefined);
      }
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [locale]);

  const connectPlaid = async (mode: PlaidConnectionMode) => {
    setBusy(mode); setError("");
    if (!portfolio.providers.plaid) {
      setError(zh ? "Plaid Production 尚未配置 Production Secret，暂时无法打开账户连接。" : "Plaid Production is missing its Production Secret, so account connection cannot open yet.");
      setBusy("");
      return;
    }
    try {
      const { link_token } = await createPlaidLinkToken();
      window.sessionStorage.setItem(PLAID_LINK_TOKEN_KEY, link_token);
      window.sessionStorage.setItem(PLAID_CONNECTION_MODE_KEY, mode);
      await launchPlaidLink(link_token, async (publicToken, institutionName) => {
        setPortfolio(await exchangePlaidToken(publicToken, institutionName));
        window.sessionStorage.removeItem(PLAID_LINK_TOKEN_KEY);
        window.sessionStorage.removeItem(PLAID_CONNECTION_MODE_KEY);
        setBusy("");
      }, () => setBusy(""), undefined, zh);
    } catch (reason) { setError(formatError(reason)); setBusy(""); }
  };
  const connectHl = async () => {
    setBusy("hyperliquid"); setError(""); setNotice("");
    try {
      setPortfolio(await connectHyperliquid(address));
      setNotice(zh ? `Hyperliquid 地址 ${address.slice(0, 6)}...${address.slice(-4)} 已连接。` : `Hyperliquid address ${address.slice(0, 6)}...${address.slice(-4)} connected.`);
      setAddress("");
    } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); }
  };
  const connectMetaMask = async () => {
    setBusy("metamask"); setError(""); setNotice("");
    try {
      if (!window.ethereum) throw new Error(zh ? "未检测到 MetaMask 浏览器扩展。" : "MetaMask browser extension was not detected.");
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" }) as string[];
      const walletAddress = accounts[0];
      if (!walletAddress) throw new Error(zh ? "MetaMask 没有返回钱包地址。" : "MetaMask did not return a wallet address.");
      setAddress(walletAddress);
      let evmEnabled = portfolio.providers.evm;
      if (!evmEnabled) {
        try {
          const fresh = await getPortfolioSnapshot(locale);
          setPortfolio(fresh);
          evmEnabled = fresh.providers.evm;
        } catch { /* keep the previous provider state */ }
      }
      if (!evmEnabled) {
        throw new Error(zh ? "MetaMask 已连接，但多链资产索引尚未配置 MORALIS_API_KEY。" : "MetaMask connected, but MORALIS_API_KEY is not configured for multi-chain assets.");
      }
      const chainHex = await window.ethereum.request({ method: "eth_chainId" }) as string;
      const chainId = Number.parseInt(chainHex, 16);
      const challenge = await createEvmWalletChallenge(walletAddress, chainId);
      const signature = await window.ethereum.request({ method: "personal_sign", params: [challenge.message, walletAddress] }) as string;
      setPortfolio(await connectEvmWallet(walletAddress, chainId, challenge.message, challenge.challenge_token, signature));
      setNotice(zh ? `MetaMask 地址 ${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)} 已验证，多链资产已计入 NAV。` : `MetaMask address ${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)} verified and added to NAV.`);
    } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); }
  };
  const sync = async (id: string) => { setBusy(id); setError(""); try { setPortfolio(await syncPortfolioAccount(id)); const { transactions } = await getPlaidInvestmentTransactions(); setPlaidTransactions(transactions); } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); } };
  const refreshPlaid = async (id: string) => {
    setBusy(`refresh:${id}`); setError(""); setNotice("");
    try {
      await requestPlaidInvestmentRefresh(id);
      setNotice(zh ? "已请求 Plaid 投资更新。完成后会通过安全回调自动同步持仓和交易。" : "Plaid Investments Refresh requested. Holdings and activity will synchronize automatically when Plaid finishes.");
    } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); }
  };
  const syncAll = async () => {
    setBusy("all"); setError(""); setNotice("");
    const failures: string[] = [];
    let latest: PortfolioSnapshot | null = null;
    for (const connection of portfolio.connections) {
      try { latest = await syncPortfolioAccount(connection.id); } catch (reason) { failures.push(`${connection.name}: ${formatError(reason)}`); }
    }
    if (latest) setPortfolio(latest);
    else setPortfolio(await getPortfolioSnapshot(locale));
    if (failures.length) setError(failures.join(" · "));
    else setNotice(zh ? "全部账户已同步。" : "All accounts synchronized.");
    setBusy("");
  };
  const disconnect = async (id: string) => { setBusy(id); setError(""); try { setPortfolio(await disconnectPortfolioAccount(id)); setAutopilot(await getPortfolioAutopilot()); } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); } };
  const saveAutopilot = async (change: Partial<PortfolioAutopilot["config"]>) => { setBusy("autopilot"); setError(""); try { setAutopilot(await updatePortfolioAutopilot(change)); } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); } };
  const runReview = async () => { setBusy("review"); setError(""); try { setAutopilot(await runPortfolioAutopilot()); } catch (reason) { setError(formatError(reason)); } finally { setBusy(""); } };

  const money = (value: number) => value.toLocaleString(locale, { style: "currency", currency: "USD", maximumFractionDigits: value !== 0 && Math.abs(value) < 0.01 ? 6 : 2 });
  const signedMoney = (value: number) => `${value >= 0 ? "+" : "-"}${money(Math.abs(value))}`;
  const pct = (value: number | null | undefined) => value === null || value === undefined ? "--" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  const quantity = (value: number) => value.toLocaleString(locale, { maximumFractionDigits: value !== 0 && Math.abs(value) < 1 ? 6 : 4 });
  const rangeDays = { "1D": 1, "1W": 7, "1M": 30, ALL: Number.POSITIVE_INFINITY }[range];
  const cutoff = Date.now() - rangeDays * 86_400_000;
  const chartData = range === "ALL" ? portfolio.nav_history : portfolio.nav_history.filter((point) => new Date(point.date).getTime() >= cutoff);
  const holdings = portfolio.holdings ?? [];
  const dailyChange = portfolio.daily_change ?? 0;
  const dailyChangePct = portfolio.daily_change_pct;
  const allocation = (() => {
    const top = holdings.slice(0, 6).map((item) => ({ name: item.chain ? `${item.symbol} · ${item.chain.toUpperCase()}` : item.symbol, value: item.value, weight: Math.max(item.weight, 0) }));
    const restWeight = holdings.slice(6).reduce((sum, item) => sum + Math.max(item.weight, 0), 0);
    const restValue = holdings.slice(6).reduce((sum, item) => sum + item.value, 0);
    if (restWeight > 0) top.push({ name: zh ? "其他" : "Other", value: restValue, weight: restWeight });
    return top;
  })();
  const accountNav = new Map((portfolio.accounts ?? []).map((item) => [item.id, item]));
  const quality = portfolio.data_quality;
  const qualityStatus = quality?.status ?? (portfolio.connected ? (portfolio.stale ? "STALE" : "CURRENT") : "NO_ACCOUNTS");
  const qualityWarningText = qualityWarning(quality, zh);
  if (snapshotLoading && !portfolio.connected) {
    return <div className="space-y-5"><LoadingSkeleton /><LoadingSkeleton /></div>;
  }
  return <div className="space-y-5">
    {snapshotError ? (
      <div className="space-y-3">
        <ErrorState
          title={zh ? "无法加载组合数据" : "Failed to load portfolio data"}
          description={zh ? `${snapshotError} 当前页面可能不是最新数据。` : `${snapshotError} The page may not show the latest data.`}
        />
        <button type="button" onClick={() => void loadSnapshot()} className="inline-flex h-10 items-center gap-2 border border-border-pg-strong px-4 text-sm font-medium hover:bg-bg-panel-muted">
          <RefreshCw className="h-4 w-4" />{zh ? "重试" : "Retry"}
        </button>
      </div>
    ) : null}
    <ResearchCard className="overflow-hidden p-0">
      <div className="p-5">
        <div className="flex items-center gap-3">
          <p className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "组合净值 NAV" : "Portfolio NAV"}</p>
          <Badge tone="neutral"><StatusDot tone={qualityStatusTone(qualityStatus)} />{qualityStatusLabel(qualityStatus, zh)}</Badge>
          {portfolio.connections.length ? <button type="button" onClick={() => void syncAll()} disabled={busy === "all"} className="ml-auto inline-flex h-7 items-center gap-1.5 border border-border-pg px-2 text-[10px] text-text-pg-muted hover:text-text-pg disabled:opacity-40">{busy === "all" ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}{zh ? "同步全部" : "Sync all"}</button> : null}
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2">
          <p className="text-4xl font-semibold tracking-normal">{portfolio.connected ? money(portfolio.nav) : "--"}</p>
          {portfolio.connected && (dailyChange !== 0 || dailyChangePct !== null && dailyChangePct !== undefined) ? <p className={`pb-1 text-sm font-medium ${dailyChange >= 0 ? "text-status-positive" : "text-status-negative"}`}>{signedMoney(dailyChange)} ({pct(dailyChangePct)}) · 24h</p> : null}
        </div>
        <div className="mt-3 flex flex-wrap gap-5 text-xs text-text-pg-muted"><span>{zh ? "可用资金" : "Available"}: {portfolio.connected ? money(portfolio.available_cash) : "--"}</span><span>{holdings.length} {zh ? "种资产" : "assets"} · {portfolio.connections.length} {zh ? "个账户" : "accounts"}</span><span>{qualityDetail(quality, zh)}</span>{portfolio.data_as_of ? <span>{zh ? "数据截至" : "As of"}: {new Date(portfolio.data_as_of).toLocaleString(locale)}</span> : null}</div>
        {qualityWarningText ? <div className="mt-4 border border-status-warning bg-status-warning/5 p-3 text-xs leading-5 text-status-warning">{qualityWarningText}</div> : null}
        <div className="mt-5 flex gap-1">{(["1D", "1W", "1M", "ALL"] as const).map((item) => <button key={item} type="button" onClick={() => setRange(item)} className={`h-7 min-w-11 px-2 font-mono text-[10px] ${range === item ? "bg-text-pg text-bg-app" : "text-text-pg-dim hover:bg-bg-panel-muted"}`}>{item}</button>)}</div>
      </div>
      {chartData.length > 1 ? <NavHistoryChart data={chartData} /> : <div className="grid h-56 place-items-center border-t border-border-pg text-sm text-text-pg-muted">{portfolio.nav_history.length > 1 ? (zh ? "该时间范围内暂无足够快照" : "Not enough snapshots in this range") : (zh ? "至少同步两次后显示真实净值曲线" : "The real NAV curve appears after at least two syncs")}</div>}
    </ResearchCard>

    {holdings.length ? <ResearchCard className="overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-border-pg p-5">
        <div>
          <div className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "资产配置" : "Asset allocation"}</div>
          <h2 className="mt-2 text-lg font-semibold">{zh ? "持仓与预言机价格" : "Holdings and oracle prices"}</h2>
        </div>
        <div className="flex gap-3 text-[10px] text-text-pg-muted">{Object.entries(portfolio.asset_classes ?? {}).map(([key, value]) => <span key={key} className="border border-border-pg px-2 py-1">{key.toUpperCase()} {money(value)}</span>)}</div>
      </div>
      <div className="grid gap-px bg-border-pg lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="bg-bg-panel p-4">{allocation.length > 1 ? <AllocationChart data={allocation} /> : <div className="grid h-64 place-items-center text-xs text-text-pg-muted">{zh ? "单一资产" : "Single asset"}</div>}</div>
        <div className="overflow-x-auto bg-bg-panel">
          <table className="w-full min-w-[560px] text-xs">
            <thead><tr className="border-b border-border-pg text-left text-[10px] uppercase text-text-pg-dim"><th className="px-4 py-3 font-medium">{zh ? "资产" : "Asset"}</th><th className="px-3 py-3 font-medium">{zh ? "链" : "Chain"}</th><th className="px-3 py-3 text-right font-medium">{zh ? "数量" : "Qty"}</th><th className="px-3 py-3 text-right font-medium">{zh ? "预言机价格" : "Oracle price"}</th><th className="px-3 py-3 text-right font-medium">24h</th><th className="px-3 py-3 text-right font-medium">{zh ? "价值" : "Value"}</th><th className="px-4 py-3 text-right font-medium">{zh ? "权重" : "Weight"}</th></tr></thead>
            <tbody className="divide-y divide-border-pg">{holdings.map((holding) => <HoldingRow key={holding.instrument} holding={holding} zh={zh} money={money} pct={pct} quantity={quantity} />)}</tbody>
          </table>
        </div>
      </div>
    </ResearchCard> : null}

    {portfolio.connections.some((connection) => connection.provider === "plaid") ? <ResearchCard className="overflow-hidden p-0">
      <div className="flex items-start justify-between border-b border-border-pg p-5">
        <div>
          <div className="text-xs font-semibold uppercase text-text-pg-muted">Plaid activity</div>
          <h2 className="mt-2 text-lg font-semibold">{zh ? "投资与现金交易" : "Investment and cash activity"}</h2>
          <p className="mt-2 text-xs leading-5 text-text-pg-muted">{zh ? "投资交易和已授权现金账户交易最多保留 24 个月。首次历史加载可能需要数分钟。" : "Investment and authorized cash-account activity is retained for up to 24 months. The first history load may take a few minutes."}</p>
        </div>
        <span className="border border-border-pg px-2 py-1 text-[10px] text-text-pg-muted">READ ONLY</span>
      </div>
      {plaidTransactions.length ? <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-xs"><thead><tr className="border-b border-border-pg text-left text-[10px] uppercase text-text-pg-dim"><th className="px-4 py-3 font-medium">{zh ? "日期" : "Date"}</th><th className="px-3 py-3 font-medium">{zh ? "活动" : "Activity"}</th><th className="px-3 py-3 font-medium">{zh ? "资产" : "Asset"}</th><th className="px-3 py-3 text-right font-medium">{zh ? "数量" : "Qty"}</th><th className="px-3 py-3 text-right font-medium">{zh ? "价格" : "Price"}</th><th className="px-3 py-3 text-right font-medium">{zh ? "金额" : "Amount"}</th><th className="px-4 py-3 text-right font-medium">{zh ? "费用" : "Fee"}</th></tr></thead><tbody className="divide-y divide-border-pg">{plaidTransactions.map((transaction) => <tr key={transaction.id} className={transaction.cancelled ? "text-text-pg-dim line-through" : ""}><td className="px-4 py-3 text-text-pg-muted">{new Date(`${transaction.date}T00:00:00`).toLocaleDateString(locale)}</td><td className="px-3 py-3"><div className="font-medium">{transaction.name}</div><div className="mt-0.5 text-[10px] uppercase text-text-pg-dim">{transaction.type}{transaction.subtype ? ` · ${transaction.subtype}` : ""}</div></td><td className="px-3 py-3">{transaction.symbol || "—"}</td><td className="px-3 py-3 text-right">{transaction.quantity ? quantity(transaction.quantity) : "—"}</td><td className="px-3 py-3 text-right">{transaction.price ? money(transaction.price) : "—"}</td><td className="px-3 py-3 text-right">{money(transaction.amount)}</td><td className="px-4 py-3 text-right">{transaction.fees ? money(transaction.fees) : "—"}</td></tr>)}</tbody></table></div> : <div className="p-5 text-sm text-text-pg-muted">{zh ? "正在准备 Plaid 交易历史。数据可用后将自动显示。" : "Plaid activity history is being prepared and will appear automatically when available."}</div>}
    </ResearchCard> : null}

    <section><div className="mb-3 text-xs font-semibold uppercase text-text-pg-muted">{zh ? "连接账户" : "Connected accounts"}</div><div className="grid gap-3 lg:grid-cols-3">
      <ProviderCard icon={<Building2 className="h-5 w-5" />} name="Plaid Investments" status={portfolio.providers.plaid ? undefined : "NEEDS CONFIG"} description={zh ? "连接券商、退休金和投资账户。" : "Connect brokerage, retirement, and investment accounts."} action={zh ? "连接 Plaid" : "Connect Plaid"} busy={busy === "plaid"} onClick={() => void connectPlaid("plaid")} disabled={!portfolio.providers.plaid} />
      <ProviderCard icon={<Link2 className="h-5 w-5" />} name="Interactive Brokers" status={portfolio.providers.plaid ? undefined : "NEEDS CONFIG"} description={zh ? "通过 Plaid 选择 Interactive Brokers LLC (US)，只读取账户和持仓。" : "Select Interactive Brokers LLC (US) in Plaid for read-only accounts and holdings."} action={zh ? "连接 IBKR（Plaid）" : "Connect IBKR with Plaid"} busy={busy === "ibkr"} onClick={() => void connectPlaid("ibkr")} disabled={!portfolio.providers.plaid} />
      <ResearchCard><div className="flex items-start justify-between"><Wallet className="h-5 w-5" /><span className="text-[10px] text-status-positive">PUBLIC API</span></div><h3 className="mt-4 font-semibold">Hyperliquid</h3><p className="mt-2 min-h-10 text-xs leading-5 text-text-pg-muted">{zh ? "使用公开钱包地址读取权益、Spot 与永续仓位。" : "Read equity, spot balances, and perpetual positions from a public wallet address."}</p><input value={address} onChange={(event) => setAddress(event.target.value)} placeholder="0x..." className="mt-4 h-10 w-full border border-border-pg bg-bg-app px-3 text-xs outline-none focus:border-border-pg-strong" /><button type="button" disabled={!address || busy === "hyperliquid"} onClick={connectHl} className="mt-2 h-10 w-full border border-border-pg-strong text-xs font-medium disabled:opacity-40">{busy === "hyperliquid" ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : (zh ? "连接 Hyperliquid" : "Connect Hyperliquid")}</button><button type="button" disabled={busy === "metamask"} onClick={connectMetaMask} className="mt-2 inline-flex h-10 w-full items-center justify-center gap-2 border border-border-pg-strong text-xs font-medium disabled:opacity-40">{busy === "metamask" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wallet className="h-4 w-4" />}{zh ? "连接 MetaMask" : "Connect MetaMask"}</button></ResearchCard>
    </div></section>
    {notice ? <div className="border border-status-positive p-3 text-sm text-status-positive">{notice}</div> : null}
    {error ? <div className="border border-status-negative p-3 text-sm text-status-negative">{error}</div> : null}
    {portfolio.connections.length ? <ResearchCard><h2 className="font-semibold">{zh ? "同步状态" : "Sync status"}</h2><div className="mt-4 divide-y divide-border-pg">{portfolio.connections.map((connection) => { const summary = accountNav.get(connection.id); return <div key={connection.id} className="flex items-center gap-3 py-3 text-sm"><div className="min-w-0 flex-1"><div className="font-medium">{connection.name}</div><div className="mt-1 text-xs text-text-pg-dim">{connection.provider.toUpperCase()} · {connection.last_sync ? new Date(connection.last_sync).toLocaleString(locale) : (zh ? "未同步" : "Not synced")}{connection.error ? ` · ${connection.error}` : ""}</div></div>{summary ? <div className="hidden text-right sm:block"><div className="text-sm font-medium">{money(summary.nav)}</div><div className={`text-[10px] ${summary.daily_change >= 0 ? "text-status-positive" : "text-status-negative"}`}>{signedMoney(summary.daily_change)} · 24h</div></div> : null}<span className={`text-xs ${connectionStatusTone(connection.status)}`}>{connectionStatusLabel(connection.status, zh)}</span>{connection.provider === "plaid" && connection.can_refresh ? <button type="button" onClick={() => void refreshPlaid(connection.id)} disabled={busy === `refresh:${connection.id}`} className="h-9 border border-border-pg px-2 text-[10px] text-text-pg-muted hover:text-text-pg disabled:opacity-40" title={zh ? "请求 Plaid 投资更新" : "Request Plaid Investments Refresh"}>{busy === `refresh:${connection.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : (zh ? "更新" : "Refresh")}</button> : null}<button type="button" onClick={() => void sync(connection.id)} className="grid h-9 w-9 place-items-center border border-border-pg" title={zh ? "同步" : "Sync"}>{busy === connection.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}</button><button type="button" onClick={() => void disconnect(connection.id)} className="grid h-9 w-9 place-items-center border border-border-pg text-status-negative" title={zh ? "断开账户" : "Disconnect account"}><Trash2 className="h-4 w-4" /></button></div>; })}</div></ResearchCard> : null}
    <ResearchCard className="overflow-hidden p-0"><div className="flex items-start justify-between border-b border-border-pg p-5"><div><div className="text-xs font-semibold uppercase text-text-pg-muted">Portfolio Autopilot</div><h2 className="mt-2 text-lg font-semibold">{zh ? "自动组合复盘" : "Automated portfolio review"}</h2><p className="mt-2 max-w-2xl text-xs leading-5 text-text-pg-muted">{zh ? "自动同步账户、检查集中度和数据新鲜度，并发现 Long Gamma 研究机会。不会下单或调仓。" : "Synchronizes accounts, checks concentration and freshness, and watches for Long Gamma research opportunities. It never places orders or rebalances."}</p></div><div className="text-right"><span className="border border-border-pg px-2 py-1 text-[10px] text-status-warning">RESEARCH ONLY</span><button type="button" disabled={busy === "autopilot" || !autopilot.account_count} onClick={() => void saveAutopilot({ enabled: !autopilot.config.enabled })} className={`mt-3 block h-8 w-14 border p-1 ${autopilot.config.enabled ? "border-status-positive" : "border-border-pg"}`} aria-label="Autopilot"><span className={`block h-5 w-5 bg-text-pg transition-transform ${autopilot.config.enabled ? "translate-x-6" : "translate-x-0"}`} /></button></div></div><div className="grid gap-px bg-border-pg md:grid-cols-2 xl:grid-cols-4"><AutopilotToggle label={zh ? "自动同步" : "Auto sync"} detail={zh ? "每 15 分钟" : "Every 15 minutes"} value={autopilot.config.auto_sync} onChange={(value) => void saveAutopilot({ auto_sync: value })} /><AutopilotToggle label={zh ? "风险提醒" : "Risk alerts"} detail={zh ? "集中度与过期数据" : "Concentration and stale data"} value={autopilot.config.risk_alerts} onChange={(value) => void saveAutopilot({ risk_alerts: value })} /><AutopilotToggle label="Long Gamma Watch" detail={zh ? "期权研究机会" : "Options research opportunities"} value={autopilot.config.long_gamma_watch} onChange={(value) => void saveAutopilot({ long_gamma_watch: value })} /><div className="bg-bg-panel p-4"><label className="text-xs font-medium">{zh ? "复盘频率" : "Review cadence"}</label><select value={autopilot.config.cadence} onChange={(event) => void saveAutopilot({ cadence: event.target.value as "daily" | "weekly" })} className="mt-3 h-9 w-full border border-border-pg bg-bg-app px-2 text-xs"><option value="daily">{zh ? "每日" : "Daily"}</option><option value="weekly">{zh ? "每周" : "Weekly"}</option></select></div></div>{autopilotSkills.length ? <div className="border-t border-border-pg p-4"><div className="text-xs font-medium">{zh ? "Autopilot Skills" : "Autopilot Skills"}</div><div className="mt-2 flex flex-wrap gap-2">{autopilotSkills.map((skill) => { const selected = autopilot.config.skill_refs.some((item) => item.skill_id === skill.skill_id); return <label key={skill.skill_id} className="flex cursor-pointer items-center gap-2 border border-border-pg px-2.5 py-2 text-xs"><input type="checkbox" checked={selected} onChange={() => { const next = selected ? autopilot.config.skill_refs.filter((item) => item.skill_id !== skill.skill_id) : [...autopilot.config.skill_refs, { skill_id: skill.skill_id, slug: skill.slug, version: skill.current_version, installation_id: skill.installation_id }]; void saveAutopilot({ skill_refs: next }); }} className="accent-[var(--foreground)]" /><span>{skill.name} · v{skill.current_version}</span></label>; })}</div></div> : null}<div className="flex flex-wrap items-center gap-3 border-t border-border-pg p-4"><button type="button" disabled={!autopilot.account_count || busy === "review"} onClick={() => void runReview()} className="inline-flex h-9 items-center gap-2 border border-border-pg-strong px-3 text-xs disabled:opacity-40">{busy === "review" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{zh ? "立即复盘" : "Run review"}</button><select value={autopilot.config.delivery} onChange={(event) => void saveAutopilot({ delivery: event.target.value as "in_app" | "telegram" | "imessage" })} className="h-9 border border-border-pg bg-bg-app px-2 text-xs"><option value="in_app">In-app</option><option value="telegram">Telegram</option><option value="imessage">iMessage</option></select><span className="text-xs text-text-pg-dim">{autopilot.last_review ? `${zh ? "上次复盘" : "Last review"}: ${new Date(autopilot.last_review).toLocaleString(locale)}` : (zh ? "尚未复盘" : "No review yet")}</span></div>{autopilot.findings.length ? <div className="border-t border-border-pg p-4"><div className="text-xs font-semibold">{zh ? "最新发现" : "Latest findings"}</div><div className="mt-3 space-y-2">{autopilot.findings.map((finding, index) => <div key={`${finding.title}-${index}`} className="flex gap-3 border border-border-pg p-3 text-xs"><span className={finding.severity === "high" ? "text-status-negative" : finding.severity === "warning" ? "text-status-warning" : "text-status-positive"}>{finding.severity.toUpperCase()}</span><span>{finding.title}</span></div>)}</div></div> : null}{!autopilot.account_count ? <p className="border-t border-border-pg p-4 text-xs text-text-pg-muted">{zh ? "请先连接一个真实账户即可开启 Autopilot。" : "Connect at least one real account to enable Autopilot."}</p> : null}</ResearchCard>
  </div>;
}
