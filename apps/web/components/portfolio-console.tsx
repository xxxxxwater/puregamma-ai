"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Link2, Loader2, Play, RefreshCw, Trash2, Wallet } from "lucide-react";
import { NavHistoryChart } from "@/components/charts";
import { ResearchCard } from "@/components/puregamma";
import { connectEvmWallet, connectHyperliquid, createEvmWalletChallenge, createPlaidLinkToken, disconnectPortfolioAccount, exchangePlaidToken, getMe, getPortfolioAutopilot, getPortfolioSnapshot, getSkillCatalog, runPortfolioAutopilot, syncPortfolioAccount, updatePortfolioAutopilot, type PortfolioAutopilot, type PortfolioSnapshot, type SkillSummary } from "@/lib/api";
import { type Locale, withLocale } from "@/i18n/routing";

declare global { interface Window { Plaid?: { create: (config: Record<string, unknown>) => { open: () => void } }; ethereum?: { request: (payload: { method: string; params?: unknown[] }) => Promise<unknown> } } }

const empty: PortfolioSnapshot = { connected: false, nav: 0, available_cash: 0, nav_history: [], connections: [], providers: { plaid: false, ibkr: false, hyperliquid: true } };
const emptyAutopilot: PortfolioAutopilot = { config: { enabled: false, cadence: "daily", auto_sync: true, risk_alerts: true, long_gamma_watch: true, delivery: "in_app", skill_refs: [] }, account_count: 0, findings: [], execution: "RESEARCH_ONLY", last_review: null };
const PLAID_LINK_TOKEN_KEY = "pg_plaid_link_token";
const PLAID_CONNECTION_MODE_KEY = "pg_plaid_connection_mode";
type PlaidConnectionMode = "plaid" | "ibkr";

async function launchPlaidLink(linkToken: string, onSuccess: (publicToken: string, institutionName: string) => Promise<void>, onExit: () => void, receivedRedirectUri?: string) {
  if (!document.querySelector("script[data-plaid-link]")) await new Promise<void>((resolve, reject) => { const script = document.createElement("script"); script.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js"; script.dataset.plaidLink = "true"; script.onload = () => resolve(); script.onerror = () => reject(new Error("Plaid Link failed to load")); document.head.appendChild(script); });
  if (!window.Plaid) throw new Error("Plaid Link is unavailable");
  window.Plaid.create({ token: linkToken, receivedRedirectUri, onSuccess: async (publicToken: string, metadata: { institution?: { name?: string } }) => onSuccess(publicToken, metadata.institution?.name || "Plaid Investments"), onExit }).open();
}

export function PortfolioConsole({ locale }: { locale: Locale }) {
  const router = useRouter();
  const zh = locale === "zh";
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot>(empty);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [autopilot, setAutopilot] = useState<PortfolioAutopilot>(emptyAutopilot);
  const [autopilotSkills, setAutopilotSkills] = useState<SkillSummary[]>([]);
  const [range, setRange] = useState<"1D" | "1W" | "1M" | "ALL">("1M");
  useEffect(() => {
    void getMe().catch((reason: Error & { status?: number }) => {
      if (reason.status === 401) router.replace(`${withLocale(locale, "/login")}?returnTo=${encodeURIComponent(withLocale(locale, "/portfolio"))}`);
    });
    void getPortfolioSnapshot(locale).then(setPortfolio);
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
      }, () => setBusy(""), window.location.href).catch((reason: Error) => {
        setError(reason.message);
        setBusy("");
      });
    }
  }, [locale, router, zh]);

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
      }, () => setBusy(""));
    } catch (reason) { setError((reason as Error).message); setBusy(""); }
  };
  const connectHl = async () => {
    setBusy("hyperliquid"); setError(""); setNotice("");
    try {
      setPortfolio(await connectHyperliquid(address));
      setNotice(zh ? `Hyperliquid 地址 ${address.slice(0, 6)}...${address.slice(-4)} 已连接。` : `Hyperliquid address ${address.slice(0, 6)}...${address.slice(-4)} connected.`);
      setAddress("");
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(""); }
  };
  const connectMetaMask = async () => {
    setBusy("metamask"); setError(""); setNotice("");
    try {
      if (!window.ethereum) throw new Error(zh ? "未检测到 MetaMask 浏览器扩展。" : "MetaMask browser extension was not detected.");
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" }) as string[];
      const walletAddress = accounts[0];
      if (!walletAddress) throw new Error(zh ? "MetaMask 没有返回钱包地址。" : "MetaMask did not return a wallet address.");
      setAddress(walletAddress);
      if (!portfolio.providers.evm) {
        throw new Error(zh ? "MetaMask 已连接，但多链资产索引尚未配置 MORALIS_API_KEY。" : "MetaMask connected, but MORALIS_API_KEY is not configured for multi-chain assets.");
      }
      const chainHex = await window.ethereum.request({ method: "eth_chainId" }) as string;
      const chainId = Number.parseInt(chainHex, 16);
      const challenge = await createEvmWalletChallenge(walletAddress, chainId);
      const signature = await window.ethereum.request({ method: "personal_sign", params: [challenge.message, walletAddress] }) as string;
      setPortfolio(await connectEvmWallet(walletAddress, chainId, challenge.message, challenge.challenge_token, signature));
      setNotice(zh ? `MetaMask 地址 ${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)} 已验证，多链资产已计入 NAV。` : `MetaMask address ${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)} verified and added to NAV.`);
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(""); }
  };
  const sync = async (id: string) => { setBusy(id); setError(""); try { setPortfolio(await syncPortfolioAccount(id)); } catch (reason) { setError((reason as Error).message); } finally { setBusy(""); } };
  const disconnect = async (id: string) => { setBusy(id); setError(""); try { setPortfolio(await disconnectPortfolioAccount(id)); setAutopilot(await getPortfolioAutopilot()); } catch (reason) { setError((reason as Error).message); } finally { setBusy(""); } };
  const saveAutopilot = async (change: Partial<PortfolioAutopilot["config"]>) => { setBusy("autopilot"); setError(""); try { setAutopilot(await updatePortfolioAutopilot(change)); } catch (reason) { setError((reason as Error).message); } finally { setBusy(""); } };
  const runReview = async () => { setBusy("review"); setError(""); try { setAutopilot(await runPortfolioAutopilot()); } catch (reason) { setError((reason as Error).message); } finally { setBusy(""); } };

  const money = (value: number) => value.toLocaleString(locale, { style: "currency", currency: "USD", maximumFractionDigits: value > 0 && value < 0.01 ? 6 : 2 });
  const rangeDays = { "1D": 1, "1W": 7, "1M": 30, ALL: Number.POSITIVE_INFINITY }[range];
  const cutoff = Date.now() - rangeDays * 86_400_000;
  const chartData = range === "ALL" ? portfolio.nav_history : portfolio.nav_history.filter((point) => new Date(point.date).getTime() >= cutoff);
  return <div className="space-y-5">
    <ResearchCard className="overflow-hidden p-0">
      <div className="p-5">
        <div className="flex items-center gap-3"><p className="text-xs font-semibold uppercase text-text-pg-muted">{zh ? "组合净值 NAV" : "Portfolio NAV"}</p>{portfolio.connected ? <span className={`text-[10px] ${portfolio.stale ? "text-status-warning" : "text-status-positive"}`}>{portfolio.stale ? "STALE" : "CURRENT"}</span> : null}</div>
        <p className="mt-3 text-4xl font-semibold tracking-normal">{portfolio.connected ? money(portfolio.nav) : "--"}</p>
        <div className="mt-3 flex flex-wrap gap-5 text-xs text-text-pg-muted"><span>{zh ? "可用资金" : "Available"}: {portfolio.connected ? money(portfolio.available_cash) : "--"}</span><span>{portfolio.connections.length} {zh ? "个账户" : "accounts"}</span>{portfolio.data_as_of ? <span>{zh ? "数据截至" : "As of"}: {new Date(portfolio.data_as_of).toLocaleString(locale)}</span> : null}</div>
        <div className="mt-5 flex gap-1">{(["1D", "1W", "1M", "ALL"] as const).map((item) => <button key={item} type="button" onClick={() => setRange(item)} className={`h-7 min-w-11 px-2 font-mono text-[10px] ${range === item ? "bg-text-pg text-bg-app" : "text-text-pg-dim hover:bg-bg-panel-muted"}`}>{item}</button>)}</div>
      </div>
      {chartData.length > 1 ? <NavHistoryChart data={chartData} /> : <div className="grid h-56 place-items-center border-t border-border-pg text-sm text-text-pg-muted">{portfolio.nav_history.length > 1 ? (zh ? "该时间范围内暂无足够快照" : "Not enough snapshots in this range") : (zh ? "至少同步两次后显示真实净值曲线" : "The real NAV curve appears after at least two syncs")}</div>}
    </ResearchCard>

    <section><div className="mb-3 text-xs font-semibold uppercase text-text-pg-muted">{zh ? "连接账户" : "Connected accounts"}</div><div className="grid gap-3 lg:grid-cols-3">
      <ProviderCard icon={<Building2 className="h-5 w-5" />} name="Plaid Investments" status={portfolio.providers.plaid ? undefined : "NEEDS CONFIG"} description={zh ? "连接券商、退休金和投资账户。" : "Connect brokerage, retirement, and investment accounts."} action={zh ? "连接 Plaid" : "Connect Plaid"} busy={busy === "plaid"} onClick={() => void connectPlaid("plaid")} disabled={false} />
      <ProviderCard icon={<Link2 className="h-5 w-5" />} name="Interactive Brokers" status={portfolio.providers.plaid ? undefined : "NEEDS CONFIG"} description={zh ? "通过 Plaid 选择 Interactive Brokers LLC (US)，只读取账户和持仓。" : "Select Interactive Brokers LLC (US) in Plaid for read-only accounts and holdings."} action={zh ? "连接 IBKR（Plaid）" : "Connect IBKR with Plaid"} busy={busy === "ibkr"} onClick={() => void connectPlaid("ibkr")} disabled={false} />
      <ResearchCard><div className="flex items-start justify-between"><Wallet className="h-5 w-5" /><span className="text-[10px] text-status-positive">PUBLIC API</span></div><h3 className="mt-4 font-semibold">Hyperliquid</h3><p className="mt-2 min-h-10 text-xs leading-5 text-text-pg-muted">{zh ? "使用公开钱包地址读取权益、Spot 与永续仓位。" : "Read equity, spot balances, and perpetual positions from a public wallet address."}</p><input value={address} onChange={(event) => setAddress(event.target.value)} placeholder="0x..." className="mt-4 h-10 w-full border border-border-pg bg-bg-app px-3 text-xs outline-none focus:border-border-pg-strong" /><button type="button" disabled={!address || busy === "hyperliquid"} onClick={connectHl} className="mt-2 h-10 w-full border border-border-pg-strong text-xs font-medium disabled:opacity-40">{busy === "hyperliquid" ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : (zh ? "连接 Hyperliquid" : "Connect Hyperliquid")}</button><button type="button" disabled={busy === "metamask"} onClick={connectMetaMask} className="mt-2 inline-flex h-10 w-full items-center justify-center gap-2 border border-border-pg-strong text-xs font-medium disabled:opacity-40">{busy === "metamask" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wallet className="h-4 w-4" />}{zh ? "连接 MetaMask" : "Connect MetaMask"}</button></ResearchCard>
    </div></section>
    {notice ? <div className="border border-status-positive p-3 text-sm text-status-positive">{notice}</div> : null}
    {error ? <div className="border border-status-negative p-3 text-sm text-status-negative">{error}</div> : null}
    {portfolio.connections.length ? <ResearchCard><h2 className="font-semibold">{zh ? "同步状态" : "Sync status"}</h2><div className="mt-4 divide-y divide-border-pg">{portfolio.connections.map((connection) => <div key={connection.id} className="flex items-center gap-3 py-3 text-sm"><div className="min-w-0 flex-1"><div className="font-medium">{connection.name}</div><div className="mt-1 text-xs text-text-pg-dim">{connection.provider.toUpperCase()} · {connection.last_sync ? new Date(connection.last_sync).toLocaleString(locale) : (zh ? "未同步" : "Not synced")}{connection.error ? ` · ${connection.error}` : ""}</div></div><span className={connection.status === "CONNECTED" ? "text-xs text-status-positive" : "text-xs text-status-negative"}>{connection.status}</span><button type="button" onClick={() => void sync(connection.id)} className="grid h-9 w-9 place-items-center border border-border-pg" title={zh ? "同步" : "Sync"}>{busy === connection.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}</button><button type="button" onClick={() => void disconnect(connection.id)} className="grid h-9 w-9 place-items-center border border-border-pg text-status-negative" title={zh ? "断开账户" : "Disconnect account"}><Trash2 className="h-4 w-4" /></button></div>)}</div></ResearchCard> : null}
    <ResearchCard className="overflow-hidden p-0"><div className="flex items-start justify-between border-b border-border-pg p-5"><div><div className="text-xs font-semibold uppercase text-text-pg-muted">Portfolio Autopilot</div><h2 className="mt-2 text-lg font-semibold">{zh ? "自动组合复盘" : "Automated portfolio review"}</h2><p className="mt-2 max-w-2xl text-xs leading-5 text-text-pg-muted">{zh ? "自动同步账户、检查集中度和数据新鲜度，并发现 Long Gamma 研究机会。不会下单或调仓。" : "Synchronizes accounts, checks concentration and freshness, and watches for Long Gamma research opportunities. It never places orders or rebalances."}</p></div><div className="text-right"><span className="border border-border-pg px-2 py-1 text-[10px] text-status-warning">RESEARCH ONLY</span><button type="button" disabled={busy === "autopilot" || !autopilot.account_count} onClick={() => void saveAutopilot({ enabled: !autopilot.config.enabled })} className={`mt-3 block h-8 w-14 border p-1 ${autopilot.config.enabled ? "border-status-positive" : "border-border-pg"}`} aria-label="Autopilot"><span className={`block h-5 w-5 bg-text-pg transition-transform ${autopilot.config.enabled ? "translate-x-6" : "translate-x-0"}`} /></button></div></div><div className="grid gap-px bg-border-pg md:grid-cols-2 xl:grid-cols-4"><AutopilotToggle label={zh ? "自动同步" : "Auto sync"} detail={zh ? "每 15 分钟" : "Every 15 minutes"} value={autopilot.config.auto_sync} onChange={(value) => void saveAutopilot({ auto_sync: value })} /><AutopilotToggle label={zh ? "风险提醒" : "Risk alerts"} detail={zh ? "集中度与过期数据" : "Concentration and stale data"} value={autopilot.config.risk_alerts} onChange={(value) => void saveAutopilot({ risk_alerts: value })} /><AutopilotToggle label="Long Gamma Watch" detail={zh ? "期权研究机会" : "Options research opportunities"} value={autopilot.config.long_gamma_watch} onChange={(value) => void saveAutopilot({ long_gamma_watch: value })} /><div className="bg-bg-panel p-4"><label className="text-xs font-medium">{zh ? "复盘频率" : "Review cadence"}</label><select value={autopilot.config.cadence} onChange={(event) => void saveAutopilot({ cadence: event.target.value as "daily" | "weekly" })} className="mt-3 h-9 w-full border border-border-pg bg-bg-app px-2 text-xs"><option value="daily">{zh ? "每日" : "Daily"}</option><option value="weekly">{zh ? "每周" : "Weekly"}</option></select></div></div>{autopilotSkills.length ? <div className="border-t border-border-pg p-4"><div className="text-xs font-medium">{zh ? "Autopilot Skills" : "Autopilot Skills"}</div><div className="mt-2 flex flex-wrap gap-2">{autopilotSkills.map((skill) => { const selected = autopilot.config.skill_refs.some((item) => item.skill_id === skill.skill_id); return <label key={skill.skill_id} className="flex cursor-pointer items-center gap-2 border border-border-pg px-2.5 py-2 text-xs"><input type="checkbox" checked={selected} onChange={() => { const next = selected ? autopilot.config.skill_refs.filter((item) => item.skill_id !== skill.skill_id) : [...autopilot.config.skill_refs, { skill_id: skill.skill_id, slug: skill.slug, version: skill.current_version, installation_id: skill.installation_id }]; void saveAutopilot({ skill_refs: next }); }} className="accent-white" /><span>{skill.name} · v{skill.current_version}</span></label>; })}</div></div> : null}<div className="flex flex-wrap items-center gap-3 border-t border-border-pg p-4"><button type="button" disabled={!autopilot.account_count || busy === "review"} onClick={() => void runReview()} className="inline-flex h-9 items-center gap-2 border border-border-pg-strong px-3 text-xs disabled:opacity-40">{busy === "review" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{zh ? "立即复盘" : "Run review"}</button><select value={autopilot.config.delivery} onChange={(event) => void saveAutopilot({ delivery: event.target.value as "in_app" | "telegram" | "imessage" })} className="h-9 border border-border-pg bg-bg-app px-2 text-xs"><option value="in_app">In-app</option><option value="telegram">Telegram</option><option value="imessage">iMessage</option></select><span className="text-xs text-text-pg-dim">{autopilot.last_review ? `${zh ? "上次复盘" : "Last review"}: ${new Date(autopilot.last_review).toLocaleString(locale)}` : (zh ? "尚未复盘" : "No review yet")}</span></div>{autopilot.findings.length ? <div className="border-t border-border-pg p-4"><div className="text-xs font-semibold">{zh ? "最新发现" : "Latest findings"}</div><div className="mt-3 space-y-2">{autopilot.findings.map((finding, index) => <div key={`${finding.title}-${index}`} className="flex gap-3 border border-border-pg p-3 text-xs"><span className={finding.severity === "high" ? "text-status-negative" : finding.severity === "warning" ? "text-status-warning" : "text-status-positive"}>{finding.severity.toUpperCase()}</span><span>{finding.title}</span></div>)}</div></div> : null}{!autopilot.account_count ? <p className="border-t border-border-pg p-4 text-xs text-text-pg-muted">{zh ? "连接至少一个真实账户后可开启 Autopilot。" : "Connect at least one real account to enable Autopilot."}</p> : null}</ResearchCard>
  </div>;
}

function ProviderCard({ icon, name, status, description, action, busy, onClick, disabled }: { icon: React.ReactNode; name: string; status?: string; description: string; action: string; busy: boolean; onClick: () => void; disabled: boolean }) { return <ResearchCard><div className="flex items-start justify-between">{icon}{status ? <span className="text-[10px] text-status-warning">{status}</span> : null}</div><h3 className="mt-4 font-semibold">{name}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-text-pg-muted">{description}</p><button type="button" disabled={disabled || busy} onClick={onClick} className="mt-4 h-10 w-full border border-border-pg-strong text-xs font-medium disabled:opacity-40">{busy ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : action}</button></ResearchCard>; }

function AutopilotToggle({ label, detail, value, onChange }: { label: string; detail: string; value: boolean; onChange: (value: boolean) => void }) { return <div className="flex items-center gap-3 bg-bg-panel p-4"><div className="min-w-0 flex-1"><div className="text-xs font-medium">{label}</div><div className="mt-1 text-[10px] text-text-pg-dim">{detail}</div></div><input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-white" /></div>; }
