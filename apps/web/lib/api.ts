import type { IntegrationRow, PositionRow, SignalRow, StrategyRow } from "@/components/puregamma";
import { defaultLocale, type Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type FetchOptions<T> = RequestInit & { fallback: T; locale?: Locale };

export async function api<T>(path: string, options: FetchOptions<T>): Promise<T> {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-PG-Locale": options.locale || defaultLocale,
        ...(options.headers || {})
      },
      credentials: "include",
      cache: "no-store"
    });
    if (!response.ok) return options.fallback;
    return response.json() as Promise<T>;
  } catch {
    return options.fallback;
  }
}

async function post<T>(path: string, body: object, fallback: T, locale: Locale = defaultLocale): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body), fallback, locale });
}

// ── Auth ────────────────────────────────────────────

export type AuthResponse = {
  user: { id: string; email: string; name: string; role: string; plan: string; credit_balance: number; stripe_customer_id?: string; avatar_url?: string | null; auth_provider?: string; email_verified?: boolean; email_verified_at?: string | null; last_login_at?: string | null; login_methods?: string[] };
  auth_header: { "X-User-Id"?: string; Authorization?: string };
  access_token?: string;
  token_type?: string;
  redirect_to?: string;
};

export async function mockLogin(email = "demo@puregamma.ai", name = "Demo User", role = "user") {
  return post<AuthResponse>("/auth/mock-login", { email, name, role }, {
    user: { id: "demo", email, name, role, plan: "Free", credit_balance: 30, auth_provider: "mock" },
    auth_header: { "X-User-Id": "demo" }
  });
}

export async function googleLogin(locale: Locale = defaultLocale) {
  const requested = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("returnTo");
  const returnTo = requested?.startsWith("/") && !requested.startsWith("//") ? requested : `/${locale}/chat`;
  const response = await fetch(`${API_URL}/auth/google/authorize?return_to=${encodeURIComponent(returnTo)}`, {
    headers: { "Content-Type": "application/json", "X-PG-Locale": locale },
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{ auth_url: string; state: string }>;
}

export async function googleCallback(code: string, state: string, locale: Locale = defaultLocale) {
  const query = new URLSearchParams({ code, state });
  const response = await fetch(`${API_URL}/auth/google/callback?${query.toString()}`, {
    headers: { "Content-Type": "application/json", "X-PG-Locale": locale },
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<AuthResponse>;
}

export async function getMe() {
  return requestStrict<{ user: AuthResponse["user"] }>("/me");
}

export async function logout() {
  return requestStrict<{ ok: boolean }>("/auth/logout", { method: "POST" });
}

// ── Onboarding ──────────────────────────────────────

export type OnboardingState = {
  step: number;
  preferred_assets: string[];
  risk_level: string;
  preferred_style: string;
  notification_channels: string[];
  imessage_recipient: string;
  telegram_chat_id: string;
  email_recipient: string;
  completed: boolean;
};

export const DEFAULT_ONBOARDING: OnboardingState = {
  step: 1,
  preferred_assets: ["BTC", "ETH", "SOL"],
  risk_level: "balanced",
  preferred_style: "risk-controlled",
  notification_channels: ["email"],
  imessage_recipient: "",
  telegram_chat_id: "",
  email_recipient: "",
  completed: false,
};

export async function saveOnboarding(userId: string, state: Partial<OnboardingState>) {
  return post<{ ok: boolean }>("/auth/onboarding", { user_id: userId, ...state }, { ok: true });
}

export type MarketAsset = {
  symbol: string;
  price: number;
  volume_24h?: number;
  funding_rate: number;
  open_interest: number | null;
  sentiment_score: number;
  risk_score?: number;
  change_24h?: number | null;
  timestamp?: string;
  source?: string;
  source_display?: string;
  source_symbol?: string | null;
  is_realtime?: boolean;
  fallback_reason?: string | null;
  asset_type?: string;
  is_mock?: boolean;
};
export type MarketSnapshotResponse = {
  mockMode?: boolean;
  live_assets?: number;
  source_summary?: string[];
  assets: MarketAsset[];
};
export type ReportRow = { id: string; title: string; report_type: string; content_markdown: string; assets: string[]; source_intelligence_id?: string; created_at: string; language?: Locale };
export type SubscriptionState = {
  plan: string;
  subscription_status: string;
  current_period_end?: string | null;
  cancel_at_period_end?: boolean;
  cancel_at?: string | null;
  credit_balance: number;
  account?: { auth_provider?: string; avatar_url?: string | null; email?: string };
  entitlement: { notification_channels: string[]; high_cost_tasks: boolean; imessage: boolean };
  checkout_mode: "session" | "payment_link";
  payment_links: Record<string, boolean>;
  primary_payment_link_configured: boolean;
};
export type DataSourceRow = { id: string; source: string; type: string; provider: string; status: string; requiredPlan: string; lastSync: string | null; lastSuccess?: string | null; error: string; itemsIngested: number; enabled: boolean; primary?: boolean; configured?: boolean; quotaLimit?: number | null; quotaRemaining?: number | null; rateLimitResetAt?: string | null; requestCount?: number; errorCount?: number; circuitOpenUntil?: string | null; retentionPolicy?: string; licenseStatus?: string; accountCount?: number };
export type DataSourcePreview = { raw: Array<{ id: string; externalId: string; url?: string | null; publishedAt?: string | null; fetchedAt: string; licenseStatus: string; retentionPolicy: string; processingStatus: string }>; normalized: Array<{ id: string; provider: string; sourceType: string; sourceName: string; title: string; summary: string; url?: string | null; author?: string | null; publishedAt?: string | null; symbols: string[]; topics: string[]; sentiment: { label?: string; score?: number }; credibilityScore: number; finalScore: number; licenseStatus: string; retentionPolicy: string }> };

export const fallbackMarket: MarketSnapshotResponse = {
  mockMode: true,
  assets: [
    { symbol: "BTC", price: 108500, volume_24h: 42000000000, funding_rate: 0.006, open_interest: 18900000000, sentiment_score: 0.62, risk_score: 46, change_24h: 1.8, source: "mock", source_symbol: "BTC", is_realtime: false },
    { symbol: "ETH", price: 5850, volume_24h: 18000000000, funding_rate: 0.004, open_interest: 9600000000, sentiment_score: 0.58, risk_score: 52, change_24h: 0.9, source: "mock", source_symbol: "ETH", is_realtime: false },
    { symbol: "SOL", price: 228, volume_24h: 7400000000, funding_rate: 0.012, open_interest: 3800000000, sentiment_score: 0.66, risk_score: 64, change_24h: 3.1, source: "mock", source_symbol: "SOL", is_realtime: false },
    { symbol: "HYPE", price: 39.2, volume_24h: 1200000000, funding_rate: 0.018, open_interest: 990000000, sentiment_score: 0.71, risk_score: 71, change_24h: 4.4, source: "mock", source_symbol: "HYPE", is_realtime: false },
    { symbol: "MSTR", price: 1840, volume_24h: 2100000000, funding_rate: 0, open_interest: null, sentiment_score: 0.55, risk_score: 67, change_24h: 2.2, source: "mock", source_display: "MOCK", source_symbol: "MSTR", is_realtime: false, asset_type: "equity", is_mock: true },
    { symbol: "STRC", price: 101.8, volume_24h: 140000000, funding_rate: 0, open_interest: null, sentiment_score: 0.49, risk_score: 49, change_24h: -0.2, source: "mock", source_display: "MOCK", source_symbol: "STRC", is_realtime: false, asset_type: "preferred_equity", is_mock: true }
  ]
};

export const fallbackSubscription: SubscriptionState = {
  plan: "Free",
  subscription_status: "inactive",
  current_period_end: null,
  cancel_at_period_end: false,
  cancel_at: null,
  credit_balance: 30,
  account: { auth_provider: "mock", avatar_url: null, email: "demo@puregamma.ai" },
  entitlement: { notification_channels: ["email"], high_cost_tasks: false, imessage: false },
  checkout_mode: "session",
  payment_links: { Pro: false, Max: false, Enterprise: false },
  primary_payment_link_configured: true
};

export const fallbackReport = {
  mockMode: true,
  reports: [
    {
      id: "fallback-report",
      title: "PureGamma Daily Crypto Brief",
      report_type: "daily_market_report",
      source_intelligence_id: "mock-shared-intel",
      content_markdown:
        "# PureGamma Daily Crypto Brief\n\n## Market Regime\nRisk-on momentum with contained leverage.\n\n## Key Signals\n- BTC leadership remains the cleanest expression of crypto beta.\n- SOL and HYPE show high beta follow-through, but funding risk is rising.\n\n## Risk\nModerate risk; favor liquid assets and explicit invalidation levels.\n\n## Disclaimer\nThis is not financial advice.",
      assets: ["BTC", "ETH", "SOL", "HYPE", "MSTR", "STRC"],
      created_at: new Date().toISOString(),
      language: "en" as Locale
    }
  ] satisfies ReportRow[]
};

export function fallbackReportForLocale(locale: Locale) {
  const title = t(locale, "reports.mock.title");
  return {
    mockMode: true,
    reports: [
      {
        id: `fallback-report-${locale}`,
        title,
        report_type: "daily_market_report",
        source_intelligence_id: "mock-shared-intel",
        content_markdown: t(locale, "reports.mock.content"),
        assets: ["BTC", "ETH", "SOL", "HYPE", "MSTR", "STRC"],
        created_at: new Date().toISOString(),
        language: locale
      }
    ] satisfies ReportRow[]
  };
}

export const fallbackSignals = {
  mockMode: true,
  signals: [
    { id: "sig-btc", asset: "BTC", signal_type: "market_structure", direction: "long_watch", confidence: 0.66, risk_score: 46, thesis: "BTC leadership remains intact.", catalyst: "ETF demand and range breakout.", invalidation: "Failed breakout.", timeframe: "1-3 weeks", created_at: new Date().toISOString() },
    { id: "sig-sol", asset: "SOL", signal_type: "relative_strength", direction: "long_watch", confidence: 0.67, risk_score: 64, thesis: "SOL beta improves as breadth expands.", catalyst: "Relative strength confirmation.", invalidation: "Loss of range support.", timeframe: "3-10 days", created_at: new Date().toISOString() },
    { id: "sig-hype", asset: "HYPE", signal_type: "trend_following", direction: "long_watch", confidence: 0.63, risk_score: 71, thesis: "HYPE trend remains convex but fragile.", catalyst: "Exchange activity and perp liquidity.", invalidation: "Loss of 7-day trend support.", timeframe: "2-8 days", created_at: new Date().toISOString() }
  ] satisfies SignalRow[]
};

export function fallbackSignalsForLocale(locale: Locale) {
  if (locale === "en") return fallbackSignals;
  return {
    mockMode: true,
    signals: [
      { id: "sig-btc", asset: "BTC", signal_type: "市场结构", direction: "long_watch", confidence: 0.66, risk_score: 46, thesis: "BTC 领先结构仍然完好。", catalyst: "ETF 需求与区间突破。", invalidation: "突破失败。", timeframe: "1-3 周", created_at: new Date().toISOString() },
      { id: "sig-sol", asset: "SOL", signal_type: "相对强度", direction: "long_watch", confidence: 0.67, risk_score: 64, thesis: "随着市场广度扩张，SOL Beta 改善。", catalyst: "相对强度确认。", invalidation: "跌破区间支撑。", timeframe: "3-10 天", created_at: new Date().toISOString() },
      { id: "sig-hype", asset: "HYPE", signal_type: "趋势跟随", direction: "long_watch", confidence: 0.63, risk_score: 71, thesis: "HYPE 趋势仍具凸性但较脆弱。", catalyst: "交易所活跃度与永续流动性。", invalidation: "跌破 7 日趋势支撑。", timeframe: "2-8 天", created_at: new Date().toISOString() }
    ] satisfies SignalRow[]
  };
}

export const fallbackPlaybooks = {
  mockMode: true,
  playbooks: [
    { strategy_name: "BTC momentum breakout", asset: "BTC", risk_score: 46, confidence: 0.68, thesis: "BTC leadership remains the cleanest crypto beta.", trigger: "Daily close above prior range high.", invalidation: "Back below breakout level.", timeframe: "1-3 weeks", expected_payoff: "Asymmetric upside if dominance expands." },
    { strategy_name: "ETH/BTC rotation", asset: "ETH", risk_score: 52, confidence: 0.61, thesis: "ETH catches up when BTC volatility cools.", trigger: "ETH/BTC reclaims 20-day average.", invalidation: "BTC dominance breakout.", timeframe: "1-4 weeks", expected_payoff: "Moderate beta catch-up." },
    { strategy_name: "MSTR premium / BTC proxy", asset: "MSTR", risk_score: 67, confidence: 0.57, thesis: "MSTR can amplify BTC, but premium compression is the key risk.", trigger: "BTC breakout with MSTR premium stable.", invalidation: "MSTR underperforms BTC materially.", timeframe: "1-3 weeks", expected_payoff: "Levered BTC proxy upside." }
  ] satisfies StrategyRow[],
  reports: []
};

export function fallbackPlaybooksForLocale(locale: Locale) {
  if (locale === "en") return fallbackPlaybooks;
  return {
    mockMode: true,
    playbooks: [
      { strategy_name: "BTC 动能突破", asset: "BTC", risk_score: 46, confidence: 0.68, thesis: "BTC 领先结构仍是最清晰的加密 Beta 表达。", trigger: "日线收盘突破前期区间高点。", invalidation: "重新跌回突破位下方。", timeframe: "1-3 周", expected_payoff: "若 BTC dominance 扩张，上行收益具非对称性。" },
      { strategy_name: "ETH/BTC 轮动", asset: "ETH", risk_score: 52, confidence: 0.61, thesis: "当 BTC 波动降温时，ETH 存在补涨窗口。", trigger: "ETH/BTC 重新站上 20 日均线。", invalidation: "BTC dominance 再次突破。", timeframe: "1-4 周", expected_payoff: "中等 Beta 补涨。" },
      { strategy_name: "MSTR 溢价 / BTC 代理", asset: "MSTR", risk_score: 67, confidence: 0.57, thesis: "MSTR 可放大 BTC 表现，但溢价压缩是核心风险。", trigger: "BTC 突破且 MSTR 溢价稳定。", invalidation: "MSTR 明显跑输 BTC。", timeframe: "1-3 周", expected_payoff: "杠杆化 BTC 代理上行。" }
    ] satisfies StrategyRow[],
    reports: []
  };
}

export const fallbackPortfolio = {
  mockMode: true,
  partialData: true,
  nav: 1284200,
  dailyPnlUsd: 18240,
  dailyPnlPct: 1.42,
  cash: 184000,
  cryptoExposure: 0.62,
  equityExposure: 0.24,
  navHistory: [
    { date: "7D", nav: 1210000 }, { date: "6D", nav: 1224000 }, { date: "5D", nav: 1218000 }, { date: "4D", nav: 1242000 }, { date: "3D", nav: 1257000 }, { date: "2D", nav: 1266000 }, { date: "1D", nav: 1284200 }
  ],
  allocation: [
    { name: "Crypto", weight: 52, value: 667784 }, { name: "Equity", weight: 24, value: 308208 }, { name: "Stablecoins", weight: 14, value: 179788 }, { name: "Cash", weight: 10, value: 128420 }
  ],
  positions: [
    { asset: "BTC", source: "On-chain", quantity: "4.2", price: 108500, value: 455700, costBasis: 389000, pnl: 66700, risk: "Medium" },
    { asset: "ETH", source: "Coinbase", quantity: "52", price: 5850, value: 304200, costBasis: 278000, pnl: 26200, risk: "Medium" },
    { asset: "MSTR", source: "Plaid Brokerage", quantity: "90", price: 1840, value: 165600, costBasis: 142000, pnl: 23600, risk: "High" },
    { asset: "USDC", source: "On-chain", quantity: "179788", price: 1, value: 179788, costBasis: 179788, pnl: 0, risk: "Low" }
  ] satisfies PositionRow[]
};

export function fallbackPortfolioForLocale(locale: Locale) {
  if (locale === "en") return fallbackPortfolio;
  return {
    ...fallbackPortfolio,
    allocation: [
      { name: "加密资产", weight: 52, value: 667784 }, { name: "权益", weight: 24, value: 308208 }, { name: "稳定币", weight: 14, value: 179788 }, { name: "现金", weight: 10, value: 128420 }
    ],
    positions: [
      { asset: "BTC", source: "链上", quantity: "4.2", price: 108500, value: 455700, costBasis: 389000, pnl: 66700, risk: "Medium" },
      { asset: "ETH", source: "Coinbase", quantity: "52", price: 5850, value: 304200, costBasis: 278000, pnl: 26200, risk: "Medium" },
      { asset: "MSTR", source: "Plaid 券商", quantity: "90", price: 1840, value: 165600, costBasis: 142000, pnl: 23600, risk: "High" },
      { asset: "USDC", source: "链上", quantity: "179788", price: 1, value: 179788, costBasis: 179788, pnl: 0, risk: "Low" }
    ] satisfies PositionRow[]
  };
}

export const fallbackIntegrations = {
  mockMode: true,
  integrations: [
    { name: "Plaid Brokerage", description: "Holdings and investment transaction sync only.", status: "stale warning", plan: "Pro", cost: 3, lastSync: "2h ago", failureReason: "Manual refresh required for demo brokerage." },
    { name: "Binance Read-only", description: "CEX balances through read-only API keys.", status: "healthy", plan: "Max", cost: 5, lastSync: "8m ago" },
    { name: "Ethereum Wallet", description: "On-chain wallet positions and stablecoins.", status: "healthy", plan: "Max", cost: 4, lastSync: "11m ago" },
    { name: "iMessage", description: "Self-hosted Mac relay for daily brief push.", status: "requires Max", plan: "Max", cost: 3, lastSync: "mock" }
  ] satisfies IntegrationRow[]
};

export function fallbackIntegrationsForLocale(locale: Locale) {
  return fallbackIntegrations;
}

export const fallbackDataSources = {
  mockMode: false,
  sources: ["CoinDesk", "RSS", "X KOL", "Bloomberg", "CoinGecko", "Binance", "Coinglass", "Glassnode", "DefiLlama", "Plaid", "Exchange", "On-chain"].map((source, index) => ({
    id: source.toLowerCase().replaceAll(" ", "-"), source,
    type: index < 4 ? "Sentiment" : index < 9 ? "Market" : "Portfolio",
    provider: source,
    status: index === 2 || index === 3 ? "requires key" : "healthy",
    requiredPlan: index > 5 ? "Max" : "Pro",
    lastSync: index === 3 ? "mock import" : `${8 + index}m ago`,
    error: index === 2 ? "X API key missing" : "",
    itemsIngested: 1200 - index * 73,
    enabled: true
  })) satisfies DataSourceRow[]
};

export function fallbackDataSourcesForLocale(locale: Locale) {
  if (locale === "en") return fallbackDataSources;
  return {
    mockMode: true,
    sources: fallbackDataSources.sources.map((source, index) => ({
      ...source,
      type: index < 4 ? t(locale, "data-sources.mockTypes.sentiment") : index < 9 ? t(locale, "data-sources.mockTypes.market") : t(locale, "data-sources.mockTypes.portfolio"),
      status: index === 2 || index === 3 ? "需要 Key" : "健康",
      lastSync: index === 3 ? "Mock 导入" : `${8 + index} 分钟前`,
      error: index === 2 ? "缺少 X API Key" : ""
    }))
  };
}

export const fallbackNautilus = {
  mockMode: true,
  strategies: ["BTC Momentum", "ETH/BTC Rotation", "SOL/HYPE Rotation", "MSTR/BTC Proxy", "Basis Funding Arbitrage", "STRC Event-driven"],
  metrics: [
    { label: "Total Return", value: "+18.4%" }, { label: "Annualized", value: "+42.1%" }, { label: "Sharpe", value: "1.62" }, { label: "Sortino", value: "2.08" },
    { label: "Max Drawdown", value: "-9.7%" }, { label: "Win Rate", value: "58%" }, { label: "Profit Factor", value: "1.41" }, { label: "Tail Risk", value: "Medium" }
  ],
  equityCurve: [
    { date: "Jan", equity: 100000 }, { date: "Feb", equity: 104200 }, { date: "Mar", equity: 101800 }, { date: "Apr", equity: 111400 }, { date: "May", equity: 116800 }, { date: "Jun", equity: 118400 }
  ]
};

export function fallbackNautilusForLocale(locale: Locale) {
  if (locale === "en") return fallbackNautilus;
  return {
    ...fallbackNautilus,
    strategies: ["BTC 动能", "ETH/BTC 轮动", "SOL/HYPE 轮动", "MSTR/BTC 代理", "基差资金费率套利", "STRC 事件驱动"],
    metrics: [
      { label: "总回报", value: "+18.4%" }, { label: "年化", value: "+42.1%" }, { label: "Sharpe", value: "1.62" }, { label: "Sortino", value: "2.08" },
      { label: "最大回撤", value: "-9.7%" }, { label: "胜率", value: "58%" }, { label: "收益因子", value: "1.41" }, { label: "尾部风险", value: "中" }
    ]
  };
}

export const fallbackDailyPush = {
  mockMode: true,
  preference: { enabled: true, channel: "iMessage", localTime: "08:30", timezone: "America/New_York", pushType: "Combined Brief" },
  history: [
    { scheduled_for: "2026-07-06 08:30", status: "sent", sent_at: "2026-07-06 08:30", failure_reason: "" },
    { scheduled_for: "2026-07-05 08:30", status: "skipped", sent_at: "", failure_reason: "iMessage entitlement denied on Free plan" }
  ]
};

export function fallbackDailyPushForLocale(locale: Locale) {
  if (locale === "en") return fallbackDailyPush;
  return {
    mockMode: true,
    preference: { enabled: true, channel: "iMessage", localTime: "08:30", timezone: "Asia/Shanghai", pushType: "组合简报" },
    history: [
      { scheduled_for: "2026-07-06 08:30", status: "已发送", sent_at: "2026-07-06 08:30", failure_reason: "" },
      { scheduled_for: "2026-07-05 08:30", status: "已跳过", sent_at: "", failure_reason: "Free 套餐无 iMessage 权限" }
    ]
  };
}

export async function getDashboard(locale: Locale = defaultLocale) {
  const [market, subscription, reports, signals] = await Promise.all([getMarketSnapshot(locale), getBillingSubscription(locale), getReports(locale), getSignals(locale)]);
  return { market, subscription, reports, signals, mockMode: Boolean((market as { mockMode?: boolean }).mockMode) };
}

export function getMarketSnapshot(locale: Locale = defaultLocale) {
  return api<MarketSnapshotResponse>("/market/snapshot", { fallback: fallbackMarket, locale });
}

export function getReports(locale: Locale = defaultLocale) {
  return api<ReturnType<typeof fallbackReportForLocale>>(`/reports?locale=${locale}`, { fallback: fallbackReportForLocale(locale), locale });
}

export function getReport(id: string, locale: Locale = defaultLocale) {
  return api<{ report: ReportRow }>(`/reports/${id}?locale=${locale}`, { fallback: { report: fallbackReportForLocale(locale).reports[0] }, locale });
}

export function sendReport(channel: string, locale: Locale = defaultLocale) {
  return post("/notifications/send", { channel, message: locale === "zh" ? "PureGamma.ai 报告已生成。本内容仅供信息和研究参考，不构成投资建议。" : "PureGamma.ai report is ready. This is not financial advice.", locale }, { delivery: { status: "mock" } }, locale);
}

export function getSignals(locale: Locale = defaultLocale) {
  return api<ReturnType<typeof fallbackSignalsForLocale>>(`/signals?locale=${locale}`, { fallback: fallbackSignalsForLocale(locale), locale });
}

export function getPortfolioSnapshot(locale: Locale = defaultLocale) {
  return Promise.resolve(fallbackPortfolioForLocale(locale));
}

export function getPortfolioPositions() {
  return Promise.resolve({ positions: fallbackPortfolio.positions, mockMode: true });
}

export function syncPortfolio() {
  return Promise.resolve({ status: "queued", mockMode: true });
}

export function getIntegrations(locale: Locale = defaultLocale) {
  if (locale === "en") return Promise.resolve(fallbackIntegrations);
  return Promise.resolve({
    mockMode: true,
    integrations: [
      { name: "Plaid 券商", description: "仅同步持仓与投资交易数据。", status: "过期警告", plan: "Pro", cost: 3, lastSync: "2 小时前", failureReason: "Demo 券商需要手动刷新。" },
      { name: "Binance 只读", description: "通过只读 API Key 同步 CEX 余额。", status: "健康", plan: "Max", cost: 5, lastSync: "8 分钟前" },
      { name: "Ethereum 钱包", description: "链上钱包持仓与稳定币资产。", status: "健康", plan: "Max", cost: 4, lastSync: "11 分钟前" },
      { name: "iMessage", description: "用于每日简报推送的自托管 Mac Relay。", status: "需要 Max", plan: "Max", cost: 3, lastSync: "Mock" }
    ] satisfies IntegrationRow[]
  });
}

export function connectPlaid() {
  return Promise.resolve({ status: "mock_link_created" });
}

export function syncExchange() {
  return Promise.resolve({ status: "queued" });
}

export function addWallet() {
  return Promise.resolve({ status: "queued" });
}

export function getDataSources(locale: Locale = defaultLocale) {
  return api<{ mockMode: boolean; sources: DataSourceRow[] }>("/admin/data-sources", { fallback: { mockMode: false, sources: [] }, locale });
}

export function syncDataSource(providerId: string) {
  return requestStrict<{ run: { id: string; status: string; error?: string } }>(`/admin/data-sources/${encodeURIComponent(providerId)}/sync`, { method: "POST" });
}

export function controlDataSource(providerId: string, enabled: boolean) {
  return requestStrict<{ source: DataSourceRow }>(`/admin/data-sources/${encodeURIComponent(providerId)}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
}

export function checkDataSource(providerId: string) {
  return requestStrict<{ source: DataSourceRow; check: { status: string; message: string } }>(`/admin/data-sources/${encodeURIComponent(providerId)}/config-check`, { method: "POST" });
}

export function getDataSourcePreview(providerId: string) {
  return requestStrict<DataSourcePreview>(`/admin/data-sources/${encodeURIComponent(providerId)}/preview`);
}

export type AgentConversation = { id: string; title: string; summary?: string | null; status: string; created_at: string; updated_at: string; archived_at?: string | null };
export type AgentSource = { id?: string; provider: string; title: string; url?: string | null; published_at?: string | null; source_timestamp?: string | null; fetched_at: string; citation_index: number };
export type AgentMessage = { id: string; conversation_id: string; role: "user" | "assistant"; content: string; status: string; model?: string | null; input_tokens: number; output_tokens: number; error_code?: string | null; error_message?: string | null; created_at: string; sources: AgentSource[] };
export type AgentStreamEvent = { event: string; data: Record<string, unknown> };

async function requestStrict<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) }
  });
  if (!response.ok) {
    const detail = await response.text();
    const error = new Error(detail || `Request failed with HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<T>;
}

export function getAgentConversations() {
  return requestStrict<{ conversations: AgentConversation[] }>("/api/agent/conversations");
}

export function createAgentConversation(title?: string) {
  return requestStrict<{ conversation: AgentConversation }>("/api/agent/conversations", { method: "POST", body: JSON.stringify({ title }) });
}

export function getAgentConversation(id: string) {
  return requestStrict<{ conversation: AgentConversation; messages: AgentMessage[] }>(`/api/agent/conversations/${encodeURIComponent(id)}`);
}

export function getAgentQuota() {
  return requestStrict<{ plan: string; used: number; limit: number; remaining: number; credit_balance: number }>("/api/agent/quota");
}

export function cancelAgentRun(runId: string) {
  return requestStrict<{ id: string; status: string }>(`/api/agent/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
}

export async function streamAgentMessage(
  conversationId: string,
  content: string,
  locale: Locale,
  signal: AbortSignal,
  onEvent: (event: AgentStreamEvent) => void
) {
  const response = await fetch(`${API_URL}/api/agent/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content, locale }),
    signal
  });
  if (!response.ok || !response.body) throw new Error(await response.text() || `Agent request failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = block.split("\n").find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = block.split("\n").find((line) => line.startsWith("data:"))?.slice(5).trim();
      if (event && data) onEvent({ event, data: JSON.parse(data) as Record<string, unknown> });
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}

export function getNautilusStrategies(locale: Locale = defaultLocale) {
  return Promise.resolve(fallbackNautilusForLocale(locale));
}

export function runNautilusBacktest() {
  return Promise.resolve({ status: "queued", result: fallbackNautilus });
}

export function getDailyPushPreferences(locale: Locale = defaultLocale) {
  return Promise.resolve(fallbackDailyPushForLocale(locale));
}

export function updateDailyPushPreferences() {
  return Promise.resolve({ status: "saved" });
}

export function sendDailyPushTest() {
  return Promise.resolve({ status: "entitlement_denied", message: "iMessage delivery is available on Max and Enterprise plans." });
}

export function getBillingSubscription(locale: Locale = defaultLocale) {
  return api<SubscriptionState>(`/billing/subscription?locale=${locale}`, { fallback: fallbackSubscription, locale });
}

export function getBillingCredits(locale: Locale = defaultLocale) {
  return api<{ credit_balance: number; usage_history: { id: string; action: string; credits_delta: number; balance_after: number; created_at: string }[] }>(`/billing/credits?locale=${locale}`, { fallback: { credit_balance: 30, usage_history: [] }, locale });
}

export function createCheckoutSession(plan_name: string, locale: Locale = defaultLocale) {
  return post("/billing/create-checkout-session", { plan_name, locale }, { checkout_url: `/${locale}/billing`, mode: "mock" }, locale);
}

export function createPaymentLinkCheckout(plan_name: string, locale: Locale = defaultLocale) {
  return post("/billing/create-payment-link-checkout", { plan_name, locale }, { checkout_url: `/${locale}/billing`, checkout_mode: "payment_link", checkout_intent_id: "mock" }, locale);
}

export function createBillingCheckout(plan_name: string, checkoutMode: "session" | "payment_link", locale: Locale = defaultLocale) {
  return checkoutMode === "payment_link" ? createPaymentLinkCheckout(plan_name, locale) : createCheckoutSession(plan_name, locale);
}

export function createPortalSession(locale: Locale = defaultLocale) {
  return post("/billing/create-portal-session", { locale }, { portal_url: `/${locale}/billing`, mode: "mock" }, locale);
}

export function cancelSubscription(locale: Locale = defaultLocale) {
  return post<SubscriptionState>("/billing/cancel-subscription", { locale }, fallbackSubscription, locale);
}

export function reactivateSubscription(locale: Locale = defaultLocale) {
  return post<SubscriptionState>("/billing/reactivate-subscription", { locale }, fallbackSubscription, locale);
}
