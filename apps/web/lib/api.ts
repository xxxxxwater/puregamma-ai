import type { IntegrationRow, PositionRow, SignalRow, StrategyRow } from "@/components/puregamma";
import { defaultLocale, type Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";
import { syncUserStateFromPayload } from "@/lib/user-state";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const AUTH_EXPIRED_EVENT = "pg:auth-expired";

function notifyAuthExpired() {
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  // Avoid redirect loops on pages that are already part of the auth flow.
  if (/^\/(en|zh)\/(login|signup|auth|verify-email|reset-password|forgot-password)(\/|$)/.test(path)) return;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

async function forwardedSessionHeaders(): Promise<Record<string, string>> {
  if (typeof window !== "undefined") return {};
  const { cookies } = await import("next/headers");
  const value = cookies().toString();
  return value ? { Cookie: value } : {};
}

function neutralizeFallback(value: unknown): unknown {
  if (Array.isArray(value)) return [];
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, neutralizeFallback(item)])
    );
  }
  if (typeof value === "number") return 0;
  if (typeof value === "boolean") return false;
  if (typeof value === "string") return "";
  return null;
}

type FetchOptions<T> = RequestInit & { fallback: T; locale?: Locale };
export type CheckoutResponse = {
  checkout_url: string;
  mode?: string;
  checkout_mode?: "session" | "payment_link";
  checkout_intent_id?: string;
  client_reference_id?: string;
};

export async function api<T>(path: string, options: FetchOptions<T>): Promise<T> {
  const production = process.env.NODE_ENV === "production";
  const allowMockFallback = !production && process.env.NEXT_PUBLIC_ALLOW_MOCK_FALLBACK === "true";
  const unavailable = (status = 0, errorCode = "API_UNAVAILABLE") => {
    const fallback = options.fallback as unknown;
    if (fallback && typeof fallback === "object" && !Array.isArray(fallback)) {
      return {
        ...(neutralizeFallback(fallback) as Record<string, unknown>),
        unavailable: true,
        error_code: errorCode,
        http_status: status,
        // Auth failures must survive fallback neutralization so pages can render
        // their "unauthorized" state instead of an empty-but-normal-looking view.
        ...(status === 401 || status === 403 ? { unauthorized: true } : {})
      } as T;
    }
    return fallback as T;
  };
  try {
    const sessionHeaders = await forwardedSessionHeaders();
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-PG-Locale": options.locale || defaultLocale,
        ...sessionHeaders,
        ...(options.headers || {})
      },
      credentials: "include",
      cache: "no-store",
      signal: options.signal || AbortSignal.timeout(8_000)
    });
    if (!response.ok) {
      if (response.status === 401) notifyAuthExpired();
      let errorCode = `HTTP_${response.status}`;
      try { const body = await response.clone().json() as { code?: string; error_code?: string }; errorCode = body.error_code || body.code || errorCode; } catch { /* non-JSON error */ }
      return allowMockFallback ? options.fallback : unavailable(response.status, errorCode);
    }
    const payload = await response.json() as T;
    syncUserStateFromPayload(payload);
    return payload;
  } catch {
    return allowMockFallback ? options.fallback : unavailable(0, "NETWORK_ERROR");
  }
}

async function post<T>(path: string, body: object, fallback: T, locale: Locale = defaultLocale): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body), fallback, locale });
}

// ── Auth ────────────────────────────────────────────

export type AuthResponse = {
  user: { id: string; email: string; name: string; role: string; plan: string; credit_balance: number; stripe_customer_id?: string; avatar_url?: string | null; auth_provider?: string; has_password?: boolean; email_verified?: boolean; email_verified_at?: string | null; last_login_at?: string | null; login_methods?: string[] };
  auth_header: { "X-User-Id"?: string; Authorization?: string };
  access_token?: string;
  token_type?: string;
  redirect_to?: string;
};

export async function mockLogin(email = "demo@puregamma.ai", name = "Demo User", role = "user") {
  return post<AuthResponse>("/auth/mock-login", { email, name, role }, {
    user: { id: "demo", email, name, role, plan: "Free", credit_balance: 150, auth_provider: "mock" },
    auth_header: { "X-User-Id": "demo" }
  });
}

export async function internalAdminLogin(username: string, password: string) {
  return requestStrict<AuthResponse>("/auth/internal-admin-login", {
    method: "POST",
    body: JSON.stringify({ username, password })
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

export function extractApiError(err: unknown): { status?: number; code?: string; message?: string; rule?: string } {
  const e = err as { status?: number; message?: string };
  let code: string | undefined;
  let message: string | undefined;
  let rule: string | undefined;
  try {
    const parsed = JSON.parse(e?.message || "");
    code = parsed?.detail?.code;
    message = parsed?.detail?.message;
    rule = parsed?.detail?.rule;
  } catch {
    /* non-JSON error body */
  }
  return { status: e?.status, code, message, rule };
}

export type CaptchaPayload = { captcha_id: string; captcha_offset: number } | { captcha_id?: undefined; captcha_offset?: undefined };

export type CaptchaPuzzle = {
  captcha_id: string;
  background: string;
  piece: string;
  piece_y: number;
  width: number;
  height: number;
  expires_in: number;
};

export async function getCaptchaPuzzle(): Promise<CaptchaPuzzle> {
  return requestStrict<CaptchaPuzzle>("/auth/captcha/puzzle");
}

export async function emailRegister(email: string, password: string, name: string, locale: Locale = defaultLocale, captcha: CaptchaPayload = {}) {
  return requestStrict<AuthResponse & { message?: string }>("/auth/email/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name, locale, ...captcha })
  });
}

export async function emailLogin(email: string, password: string, captcha: CaptchaPayload = {}) {
  return requestStrict<AuthResponse>("/auth/email/login", {
    method: "POST",
    body: JSON.stringify({ email, password, ...captcha })
  });
}

export async function emailVerify(token: string) {
  return requestStrict<AuthResponse & { message?: string }>("/auth/email/verify", {
    method: "POST",
    body: JSON.stringify({ token })
  });
}

export async function resendVerificationEmail(email: string) {
  return requestStrict<{ message: string }>("/auth/email/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email })
  });
}

export async function forgotPassword(email: string) {
  return requestStrict<{ message: string }>("/auth/email/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email })
  });
}

export async function resetPassword(token: string, password: string) {
  return requestStrict<AuthResponse & { message?: string }>("/auth/email/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password })
  });
}

export async function changePassword(currentPassword: string, newPassword: string) {
  return requestStrict<AuthResponse & { message?: string }>("/auth/email/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
  });
}

export async function setPassword(newPassword: string) {
  return requestStrict<AuthResponse & { message?: string }>("/auth/email/set-password", {
    method: "POST",
    body: JSON.stringify({ current_password: "", new_password: newPassword })
  });
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

export async function saveOnboarding(state: Partial<OnboardingState> & Record<string, unknown>) {
  return requestStrict<{ ok: boolean; user: AuthResponse["user"] }>("/auth/onboarding", {
    method: "POST",
    body: JSON.stringify(state)
  });
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
  billing_mode?: string;
  account?: { auth_provider?: string; avatar_url?: string | null; email?: string };
  entitlement: { notification_channels: string[]; high_cost_tasks: boolean; imessage: boolean };
  checkout_mode: "session" | "payment_link";
  payment_links: Record<string, boolean>;
  primary_payment_link_configured: boolean;
  unavailable?: boolean;
  error_code?: string;
  http_status?: number;
};
export type DataSourceRow = { id: string; source: string; type: string; provider: string; status: string; requiredPlan: string; lastSync: string | null; lastSuccess?: string | null; error: string; itemsIngested: number; enabled: boolean; primary?: boolean; configured?: boolean; entitled?: boolean; sourceTimestamp?: string | null; freshnessSeconds?: number | null; stale?: boolean; failureReason?: string | null; redistributionAllowed?: boolean; isMock?: boolean; quotaLimit?: number | null; quotaRemaining?: number | null; rateLimitResetAt?: string | null; requestCount?: number; errorCount?: number; circuitOpenUntil?: string | null; retentionPolicy?: string; licenseStatus?: string; accountCount?: number };
export type DataSourcePreview = { raw: Array<{ id: string; externalId: string; url?: string | null; publishedAt?: string | null; fetchedAt: string; licenseStatus: string; retentionPolicy: string; processingStatus: string }>; normalized: Array<{ id: string; provider: string; sourceType: string; sourceName: string; title: string; summary: string; url?: string | null; author?: string | null; publishedAt?: string | null; symbols: string[]; topics: string[]; sentiment: { label?: string; score?: number }; credibilityScore: number; finalScore: number; licenseStatus: string; retentionPolicy: string }> };

export const fallbackMarket: MarketSnapshotResponse = {
  mockMode: false,
  live_assets: 0,
  source_summary: [],
  assets: []
};

export const fallbackSubscription: SubscriptionState = {
  plan: "",
  subscription_status: "unavailable",
  current_period_end: null,
  cancel_at_period_end: false,
  cancel_at: null,
  credit_balance: 0,
  billing_mode: "unavailable",
  account: { auth_provider: "", avatar_url: null, email: "" },
  entitlement: { notification_channels: [], high_cost_tasks: false, imessage: false },
  checkout_mode: "session",
  payment_links: { Pro: false, Max: false, Enterprise: false },
  primary_payment_link_configured: false,
  unavailable: true
};

export const fallbackReport = {
  unavailable: true,
  mockMode: false,
  reports: [] as ReportRow[]
};

export function fallbackReportForLocale(locale: Locale) {
  return {
    unavailable: true,
    mockMode: false,
    reports: [] as ReportRow[]
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
    { name: "Telegram", description: "Research briefs and account-risk notifications.", status: "requires key", plan: "Pro", cost: 1, lastSync: "not configured" },
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

export type DailyPushPreference = { enabled: boolean; timezone: string; local_time: string; channel: "email" | "telegram" | "imessage"; locale: string; include_portfolio: boolean; include_market: boolean; include_signals: boolean; include_risk: boolean; include_sentiment: boolean; quiet_hours: Record<string, unknown>; max_length: number; next_delivery_at: string | null; recipient: string | null; recipient_verified_at: string | null };
export type DeliveryRecord = { id: string; channel: string; status: string; created_at: string; sent_at: string | null; provider_response: { reason?: string } };

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
  const [market, subscription, reports] = await Promise.all([getMarketSnapshot(locale), getBillingSubscription(locale), getReports(locale)]);
  return { market, subscription, reports, mockMode: Boolean((market as { mockMode?: boolean }).mockMode) };
}

export type GatewayKey = {
  id: string;
  name: string;
  prefix: string;
  last_four: string;
  status: "active" | "paused" | "revoked";
  rate_limit_rpm: number;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type GatewayCatalogPrice = {
  amount: string;
  unit: string;
  description?: string;
};

export type GatewayCatalogModel = {
  id: string;
  display_name: string;
  provider: string;
  provider_display_name: string;
  provider_model_id: string;
  capabilities: Record<string, boolean | number | string>;
  metadata: Record<string, string>;
  availability: "available" | "pending_approval" | "provider_disabled" | "setup_required";
  pricing: {
    currency: string;
    official: Record<string, GatewayCatalogPrice>;
    final: Record<string, GatewayCatalogPrice>;
    status: "active" | "pending" | "catalog_unapproved" | "requires_currency_policy" | string;
  } | null;
  source_reference: string | null;
};

export type GatewayCatalog = {
  gateway_enabled: boolean;
  markup_bps: number | null;
  updated_at: string | null;
  models: GatewayCatalogModel[];
  unavailable?: boolean;
};

const emptyGatewayCatalog: GatewayCatalog = {
  gateway_enabled: false,
  markup_bps: null,
  updated_at: null,
  models: [],
  unavailable: true,
};

export function getGatewayCatalog(locale: Locale = defaultLocale) {
  return api<GatewayCatalog>("/gateway/catalog", { fallback: emptyGatewayCatalog, locale });
}

export type GatewayDashboard = {
  account: { status: string; monthly_spend_limit_usd: string; current_month_spend_usd: string; month_started_at: string };
  wallet: { currency: string; available_balance_usd: string; lifetime_credited_usd: string; lifetime_debited_usd: string; topup_min_usd: string; topup_max_usd: string };
  subscription: { plan: string; stripe_customer_id: string | null };
  spend_usd: { today: string; month: string; lifetime: string };
  models: Array<{ model: string; requests: number; input_tokens: number; output_tokens: number; cost_usd: string }>;
  wallet_ledger: Array<{ id: string; entry_type: string; amount_usd: string; balance_after_usd: string; topup_intent_id: string | null; gateway_request_log_id: string | null; metadata: Record<string, unknown>; created_at: string }>;
  topups: Array<{ id: string; public_reference: string; amount_usd: string; currency: string; status: string; created_at: string; completed_at: string | null }>;
  unavailable?: boolean;
};

export type GatewayRequest = {
  id: string;
  request_id: string;
  model: string;
  status: string;
  http_status: number;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cache_tokens: number;
  reasoning_tokens: number;
  cost_usd: string;
  provider_cost_usd: string;
  error_code: string | null;
  created_at: string;
};

const emptyGatewayDashboard: GatewayDashboard = {
  account: { status: "unavailable", monthly_spend_limit_usd: "0", current_month_spend_usd: "0", month_started_at: "" },
  wallet: { currency: "USD", available_balance_usd: "0", lifetime_credited_usd: "0", lifetime_debited_usd: "0", topup_min_usd: "5.00", topup_max_usd: "10000.00" },
  subscription: { plan: "", stripe_customer_id: null },
  spend_usd: { today: "0", month: "0", lifetime: "0" },
  models: [],
  wallet_ledger: [],
  topups: [],
  unavailable: true
};

export function getGatewayDashboard(locale: Locale = defaultLocale) {
  return api<GatewayDashboard>("/gateway/dashboard", { fallback: emptyGatewayDashboard, locale });
}

export function getGatewayKeys(locale: Locale = defaultLocale) {
  return api<{ keys: GatewayKey[]; limit: number; unavailable?: boolean }>("/gateway/keys", { fallback: { keys: [], limit: 10, unavailable: true }, locale });
}

export function getGatewayRequests(locale: Locale = defaultLocale) {
  return api<{ requests: GatewayRequest[]; total: number; unavailable?: boolean }>("/gateway/requests?limit=20", { fallback: { requests: [], total: 0, unavailable: true }, locale });
}

export type GatewayUsageBucket = {
  bucket: string;
  requests: number;
  success: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  cache_tokens: number;
  reasoning_tokens: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  cost_usd: string;
};

export type GatewayUsageTotals = {
  requests: number;
  success: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  cache_tokens: number;
  reasoning_tokens: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  cost_usd: string;
};

export type GatewayUsageBreakdownRow = {
  model?: string;
  api_key_id?: string | null;
  name?: string;
  prefix?: string;
  requests: number;
  success: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  cache_tokens: number;
  reasoning_tokens: number;
  avg_latency_ms: number;
  cost_usd: string;
};

export type GatewayUsage = {
  start: string;
  end: string;
  granularity: "hour" | "day";
  buckets: GatewayUsageBucket[];
  totals: GatewayUsageTotals;
  by_model: GatewayUsageBreakdownRow[];
  by_key: GatewayUsageBreakdownRow[];
  unavailable?: boolean;
};

const emptyGatewayUsage: GatewayUsage = {
  start: "",
  end: "",
  granularity: "day",
  buckets: [],
  totals: { requests: 0, success: 0, errors: 0, input_tokens: 0, output_tokens: 0, cache_tokens: 0, reasoning_tokens: 0, avg_latency_ms: 0, max_latency_ms: 0, cost_usd: "0" },
  by_model: [],
  by_key: [],
  unavailable: true
};

export function getGatewayUsage(locale: Locale = defaultLocale, params: { start?: string; end?: string; granularity?: "hour" | "day"; model?: string; api_key_id?: string } = {}) {
  const query = new URLSearchParams();
  if (params.start) query.set("start", params.start);
  if (params.end) query.set("end", params.end);
  if (params.granularity) query.set("granularity", params.granularity);
  if (params.model) query.set("model", params.model);
  if (params.api_key_id) query.set("api_key_id", params.api_key_id);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return api<GatewayUsage>(`/gateway/usage${suffix}`, { fallback: emptyGatewayUsage, locale });
}

export function createGatewayKey(name: string) {
  return requestStrict<{ key: string; api_key: GatewayKey }>("/gateway/keys", { method: "POST", body: JSON.stringify({ name }) });
}

export function changeGatewayKeyStatus(keyId: string, status: "active" | "paused" | "revoked") {
  if (status === "revoked") return requestStrict<{ ok: boolean }>(`/gateway/keys/${keyId}`, { method: "DELETE" });
  return requestStrict<{ api_key: GatewayKey }>(`/gateway/keys/${keyId}/${status === "active" ? "resume" : "pause"}`, { method: "POST" });
}

export function rotateGatewayKey(keyId: string) {
  return requestStrict<{ key: string; api_key: GatewayKey }>(`/gateway/keys/${keyId}/rotate`, { method: "POST" });
}

export function createGatewayTopup(amount_usd: string, locale: Locale) {
  return requestStrict<{ checkout_url: string; mode: "stripe" | "mock"; checkout_mode: "gateway_topup"; topup: { id: string; amount_usd: string; currency: string; status: string } }>("/gateway/topups", {
    method: "POST",
    body: JSON.stringify({ amount_usd, locale })
  });
}

export type GatewayAdminProvider = { id: string; name: string; display_name: string; enabled: boolean; health_status: string; last_health_at: string | null; last_error: string | null; models: number };
export type GatewayPriceRevision = { id: string; model_id: string; status: string; currency: string; markup_bps: number; official_prices: Record<string, unknown>; final_prices: Record<string, unknown>; source_type: string; source_reference: string | null; synced_at: string; approved_at: string | null };
export type GatewayMetrics = { revenue_usd: string; provider_cost_usd: string; profit_usd: string; prepaid_liability_usd: string; requests: number };
export type GatewayAdminAccount = {
  user_id: string;
  email: string;
  name: string;
  plan: string;
  account_status: "active" | "suspended";
  monthly_spend_limit_usd: string;
  current_month_spend_usd: string;
  lifetime_spend_usd: string;
  wallet_balance_usd: string;
  active_key_count: number;
  last_login_at: string | null;
};

export function getGatewayAdminProviders() { return requestStrict<{ providers: GatewayAdminProvider[]; registered_plugins: string[] }>("/admin/gateway/providers"); }
export function getGatewayPendingPrices() { return requestStrict<{ revisions: GatewayPriceRevision[] }>("/admin/gateway/prices/pending"); }
export function getGatewayMetrics() { return requestStrict<GatewayMetrics>("/admin/gateway/metrics"); }
export function getGatewayPricingPolicy() { return requestStrict<{ policy: { markup_bps: number } }>("/admin/gateway/pricing/policy"); }
export function syncGatewayProviders() { return requestStrict<{ syncs: unknown[] }>("/admin/gateway/sync", { method: "POST" }); }
export function approveGatewayPrice(revisionId: string) { return requestStrict<{ revision: GatewayPriceRevision }>(`/admin/gateway/prices/${revisionId}/approve`, { method: "POST" }); }
export function updateGatewayMarkup(markupBps: number) { return requestStrict<{ policy: { markup_bps: number } }>("/admin/gateway/pricing/markup", { method: "PUT", body: JSON.stringify({ markup_bps: markupBps }) }); }
export function setGatewayProviderEnabled(providerName: string, enabled: boolean) { return requestStrict<{ id: string; name: string; enabled: boolean }>(`/admin/gateway/providers/${providerName}`, { method: "PUT", body: JSON.stringify({ enabled }) }); }
export function healthcheckGatewayProviders() { return requestStrict<{ providers: Array<{ provider: string; healthy: boolean; status: string; error?: string | null }> }>("/admin/gateway/providers/healthcheck", { method: "POST" }); }
export function getGatewayAdminAccounts() { return requestStrict<{ accounts: GatewayAdminAccount[]; total: number; limit: number; offset: number }>("/admin/gateway/accounts?limit=100"); }
export function updateGatewayAccount(userId: string, payload: { status: "active" | "suspended"; monthly_spend_limit_usd: number }) { return requestStrict<{ account: GatewayAdminAccount }>(`/admin/gateway/accounts/${userId}`, { method: "PATCH", body: JSON.stringify(payload) }); }

export function getMarketSnapshot(locale: Locale = defaultLocale) {
  return api<MarketSnapshotResponse>("/market/snapshot", { fallback: { mockMode: false, live_assets: 0, source_summary: [], assets: [] }, locale });
}

export function getReports(locale: Locale = defaultLocale) {
  return api<ReturnType<typeof fallbackReportForLocale>>(`/reports?locale=${locale}`, { fallback: fallbackReportForLocale(locale), locale });
}

export function getReport(id: string, locale: Locale = defaultLocale) {
  return api<{ report: ReportRow }>(`/reports/${id}?locale=${locale}`, { fallback: { report: fallbackReportForLocale(locale).reports[0] }, locale });
}

export function sendReport(channel: string, locale: Locale = defaultLocale) {
  return requestStrict<{ delivery: { status: string } }>("/notifications/send", { method: "POST", body: JSON.stringify({ channel, message: locale === "zh" ? "PureGamma AI 报告已生成。使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。" : "PureGamma AI report is ready. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", locale }) });
}

export function getSignals(locale: Locale = defaultLocale) {
  return api<ReturnType<typeof fallbackSignalsForLocale>>(`/signals?locale=${locale}`, { fallback: fallbackSignalsForLocale(locale), locale });
}

export function getPortfolioSnapshot(locale: Locale = defaultLocale) {
  return api<PortfolioSnapshot>("/portfolio", { fallback: emptyPortfolioSnapshot(), locale });
}

export type PortfolioConnection = { id: string; provider: string; name: string; status: string; last_sync: string | null; error?: string | null; can_refresh?: boolean; refresh_requested_at?: string | null };
export type PortfolioHolding = { symbol: string; instrument: string; name: string; chain: string | null; quantity: number; price: number; value: number; weight: number; change_24h: number; change_24h_pct: number; asset_class: string; native: boolean; verified: boolean; priced: boolean; logo?: string | null };
export type PortfolioAccountSummary = { id: string; provider: string; name: string; status: string; nav: number; available_cash: number; daily_change: number; as_of: string | null };
export type PortfolioQualityAccount = { id: string; provider: string; name: string; status: "CURRENT" | "STALE" | "PENDING_SYNC"; as_of: string | null };
export type PortfolioDataQuality = { status: "NO_ACCOUNTS" | "PENDING_SYNC" | "PARTIAL" | "STALE" | "CURRENT"; total_accounts: number; synced_accounts: number; source_count: number; current_accounts: PortfolioQualityAccount[]; stale_accounts: PortfolioQualityAccount[]; missing_accounts: PortfolioQualityAccount[] };
export type PortfolioSnapshot = { connected: boolean; partial?: boolean; stale?: boolean; data_as_of?: string | null; data_quality?: PortfolioDataQuality; nav: number; available_cash: number; daily_change?: number; daily_change_pct?: number | null; nav_history: Array<{ date: string; nav: number }>; holdings?: PortfolioHolding[]; asset_classes?: Record<string, number>; accounts?: PortfolioAccountSummary[]; connections: PortfolioConnection[]; providers: { plaid: boolean; plaid_refresh?: boolean; plaid_cash_transactions?: boolean; plaid_webhooks?: boolean; ibkr: boolean; hyperliquid: boolean; evm?: boolean; binance?: boolean; okx?: boolean; bybit?: boolean } };
export type PortfolioInvestmentTransaction = { id: string; account_id: string; provider_account_id: string; date: string; transaction_datetime?: string | null; name: string; symbol?: string | null; type: string; subtype?: string | null; quantity: number; price: number; amount: number; fees: number; currency?: string | null; cancelled: boolean };

export function emptyPortfolioSnapshot(): PortfolioSnapshot {
  return {
    connected: false,
    partial: false,
    stale: false,
    data_as_of: null,
    data_quality: { status: "NO_ACCOUNTS", total_accounts: 0, synced_accounts: 0, source_count: 0, current_accounts: [], stale_accounts: [], missing_accounts: [] },
    nav: 0,
    available_cash: 0,
    daily_change: 0,
    daily_change_pct: null,
    nav_history: [],
    holdings: [],
    asset_classes: {},
    accounts: [],
    connections: [],
    providers: { plaid: false, ibkr: false, hyperliquid: true, evm: false },
  };
}

export function createPlaidLinkToken() { return requestStrict<{ link_token: string }>("/portfolio/plaid/link-token", { method: "POST" }); }
export function exchangePlaidToken(publicToken: string, institutionName: string) { return requestStrict<PortfolioSnapshot>("/portfolio/plaid/exchange", { method: "POST", body: JSON.stringify({ public_token: publicToken, institution_name: institutionName }) }); }
export function connectHyperliquid(address: string) { return requestStrict<PortfolioSnapshot>("/portfolio/hyperliquid/connect", { method: "POST", body: JSON.stringify({ address }) }); }
export function createEvmWalletChallenge(address: string, chainId: number) { return requestStrict<{ message: string; challenge_token: string; expires_in: number }>("/portfolio/evm/challenge", { method: "POST", body: JSON.stringify({ address, chain_id: chainId }) }); }
export function connectEvmWallet(address: string, chainId: number, message: string, challengeToken: string, signature: string) { return requestStrict<PortfolioSnapshot>("/portfolio/evm/connect", { method: "POST", body: JSON.stringify({ address, chain_id: chainId, message, challenge_token: challengeToken, signature }) }); }
export function getIbkrAuthorizeUrl() { return requestStrict<{ authorize_url: string }>("/portfolio/ibkr/authorize"); }
export function exchangeIbkrCode(code: string, state: string) { return requestStrict<PortfolioSnapshot>(`/portfolio/ibkr/exchange?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`, { method: "POST" }); }
export function syncPortfolioAccount(accountId: string) { return requestStrict<PortfolioSnapshot>(`/portfolio/accounts/${encodeURIComponent(accountId)}/sync`, { method: "POST" }); }
export function requestPlaidInvestmentRefresh(accountId: string) { return requestStrict<{ account_id: string; status: string; request_id?: string | null; retry_after_seconds: number }>(`/portfolio/accounts/${encodeURIComponent(accountId)}/plaid-refresh`, { method: "POST" }); }
export function getPlaidInvestmentTransactions(accountId?: string, limit = 100) { const query = new URLSearchParams({ limit: String(limit) }); if (accountId) query.set("account_id", accountId); return requestStrict<{ transactions: PortfolioInvestmentTransaction[] }>(`/portfolio/plaid/transactions?${query.toString()}`); }
export function disconnectPortfolioAccount(accountId: string) { return requestStrict<PortfolioSnapshot>(`/portfolio/accounts/${encodeURIComponent(accountId)}`, { method: "DELETE" }); }
export type PortfolioAutopilot = { config: { enabled: boolean; cadence: "daily" | "weekly"; auto_sync: boolean; risk_alerts: boolean; long_gamma_watch: boolean; delivery: "in_app" | "telegram" | "imessage"; skill_refs: SkillContextRef[] }; account_count: number; findings: Array<{ severity: string; title: string }>; concentration?: Record<string, number>; execution: "RESEARCH_ONLY"; last_review: string | null };
export function getPortfolioAutopilot() { return requestStrict<PortfolioAutopilot>("/portfolio/autopilot"); }
export function updatePortfolioAutopilot(config: Partial<PortfolioAutopilot["config"]>) { return requestStrict<PortfolioAutopilot>("/portfolio/autopilot", { method: "PUT", body: JSON.stringify(config) }); }
export function runPortfolioAutopilot() { return requestStrict<PortfolioAutopilot>("/portfolio/autopilot/run", { method: "POST" }); }

export function getPortfolioPositions() {
  return requestStrict<{ positions: PositionRow[]; status: string }>("/portfolio/positions");
}

export function syncPortfolio() {
  return Promise.reject(new Error("Select a connected portfolio account to synchronize"));
}

export async function getIntegrations(locale: Locale = defaultLocale) {
  const portfolio = await api<PortfolioSnapshot & { unavailable?: boolean }>("/portfolio", {
    fallback: { ...emptyPortfolioSnapshot(), providers: { plaid: false, ibkr: false, hyperliquid: false, evm: false }, unavailable: true },
    locale
  });
  return {
    mockMode: false,
    unavailable: portfolio.unavailable,
    integrations: (portfolio.connections || []).map((connection) => ({
      name: connection.name,
      description: `${connection.provider.toUpperCase()} read-only portfolio connection`,
      status: connection.status,
      plan: "",
      cost: 0,
      lastSync: connection.last_sync || (locale === "zh" ? "尚未同步" : "not synchronized"),
      failureReason: connection.error || undefined
    })) satisfies IntegrationRow[]
  };
}

export function connectPlaid() {
  return Promise.reject(new Error("Use the authenticated Plaid Link flow"));
}

export function syncExchange() {
  return Promise.reject(new Error("Select a connected exchange account to synchronize"));
}

export function addWallet() {
  return Promise.reject(new Error("Select a supported wallet connector"));
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
export type AgentAttachment = { name: string; content: string; mime: string };
export type SkillContextRef = { skill_id: string; slug: string; version: string; installation_id?: string | null };
export type AgentRuntimePlan = {
  intent: string;
  goal?: string;
  assets: string[];
  horizon?: string | null;
  skill_slugs?: string[];
  data_sources?: string[];
  evidence_requirements: string[];
  clarification_recommended?: boolean;
  auto_selected_skills?: boolean;
  next_actions?: string[];
  runtime_plan_version?: string;
};
export type AgentEvidenceSummary = { schema_version?: string; sufficient: boolean; missing: string[]; record_count: number; source_count: number; provider_count: number; kinds: string[] };
export type SkillSummary = {
  skill_id: string;
  slug: string;
  name: string;
  description: string;
  publisher: string;
  scope: "personal" | "workspace" | "official" | "marketplace";
  status: string;
  current_version: string;
  asset_classes: string[];
  data_sources: string[];
  tool_allowlist: string[];
  risk_level: "low" | "medium" | "high" | "execution_sensitive";
  allow_autopilot: boolean;
  allow_order_intent: boolean;
  billing_type: "free" | "included" | "paid" | "enterprise";
  evidence: { required: boolean; require_source_timestamp: boolean; require_citation_links: boolean };
  runtime: { max_calls_per_hour: number; max_credits_per_run: number; timeout_seconds: number; human_confirmation_required: boolean };
  installation_id?: string | null;
  installed: boolean;
  enabled: boolean;
};
export type AgentContext = { data_sources: string[]; skills: Array<string | SkillContextRef>; skill_refs?: SkillContextRef[]; custom_prompt: string; attachments: AgentAttachment[]; model?: string; runtime?: AgentRuntimePlan; evidence?: AgentEvidenceSummary };
export type AgentMessage = { id: string; conversation_id: string; role: "user" | "assistant"; content: string; status: string; model?: string | null; input_tokens: number; output_tokens: number; credits_used?: number | null; credits_refunded?: boolean; error_code?: string | null; error_message?: string | null; created_at: string; context?: AgentContext; sources: AgentSource[] };
export type AgentStreamEvent = { event: string; data: Record<string, unknown> };
export type SecretaryMessage = { id: string; role: "user" | "assistant"; content: string; created_at: string };
export type SecretarySkill = { id: string; status: "active" | "confirmation_required" | "setup_required" | "available" | "planned"; risk: "low" | "medium" | "high" };
export type SecretaryState = { conversation_id: string | null; messages: SecretaryMessage[]; voice: { id: string; name: string; fixed: boolean }; skills: SecretarySkill[]; memory: { enabled: boolean; isolated_by_user: boolean }; billing: { credits_per_reply: number; credit_balance: number } };
export type RuntimeStrategy = { id: string; name: string; description: string; status: string; current_version: number; execution_mode: string; draft: { instruments: string[]; venues: string[]; timeframe: string; strategy_type: string; strategy_subtype?: string; sentiment_sources: string[]; max_notional: number; leverage: number; stop_loss?: number | null; max_daily_loss: number; max_drawdown: number }; latest_run?: RuntimeRun | null; created_at: string; updated_at: string };
export type ActivationPreviewSummary = { strategy_name: string; strategy_version: number; execution_mode: string; instruments: string[]; venues: string[]; timeframe: string; strategy_type: string; strategy_subtype?: string; direction: string; max_position: number; max_notional: number; leverage: number; stop_loss?: number | null; max_daily_loss: number; max_drawdown: number; estimated_fee_bps?: number | null; estimated_slippage_bps?: number | null; output_contract: string; expires_minutes: number };
export type RuntimeRun = { id: string; strategy_id: string; strategy_version: number; account_id?: string | null; runtime_run_id: string; execution_mode: string; status: string; started_at?: string | null; stopped_at?: string | null; performance: Record<string, number>; error_code?: string | null; error_message?: string | null };
export type TradingAccount = { id: string; name: string; venue: string; account_type: string; base_currency: string; status: string; permissions: Record<string, boolean>; created_at: string };
export type TradingPosition = { id: string; account_id: string; strategy_id?: string | null; instrument: string; quantity: number; side: string; average_price: number; mark_price: number; unrealized_pnl: number; realized_pnl: number; leverage: number; captured_at: string };
export type TradingOrder = { id: string; account_id: string; strategy_id?: string | null; client_order_id: string; sequence: number; state: string; instrument: string; side: string; quantity: number; filled_quantity: number; remaining_quantity: number; reduce_only: boolean; created_at: string };
export type TradingPerformance = { account_id: string; balance: number; equity: number; available_margin: number; daily_pnl: number; drawdown: number; exposure: number; stale: boolean; captured_at: string };
export type OptionInstrument = { instrument: string; underlying: string; option_type: string; strike: number; expiry: string; bid?: number | null; ask?: number | null; mark_price?: number | null; mark_iv?: number | null; volume_24h: number; open_interest: number; spread_pct?: number | null; greeks: { delta?: number; gamma?: number; theta?: number; vega?: number }; timestamp: string };
export type LongGammaCandidate = OptionInstrument & { days_to_expiry: number; gamma_theta_ratio: number; research_score: number; rationale: string[]; execution_enabled: false };
export type EarningsGammaCandidate = { symbol: string; name: string; earnings_date: string; sector: string; market_cap_category: string; research_score: number; rationale: string[]; news_snippet: string; execution_enabled: false; updated_at: string };

async function requestStrict<T>(path: string, init: RequestInit = {}): Promise<T> {
  const sessionHeaders = await forwardedSessionHeaders();
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...sessionHeaders, ...(init.headers || {}) }
  });
  if (!response.ok) {
    if (response.status === 401) notifyAuthExpired();
    const detail = await response.text();
    const error = new Error(detail || `Request failed with HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  const payload = await response.json() as T;
  syncUserStateFromPayload(payload);
  return payload;
}

export type AdminCreditAccount = {
  id: string;
  email: string;
  name: string;
  role: string;
  plan: string;
  credit_balance: number;
  stripe_customer_id?: string | null;
  auth_provider: string;
  created_at: string;
  updated_at: string;
};

export type AdminCreditLedgerEntry = {
  id: string;
  action: string;
  credits_delta: number;
  balance_after: number;
  idempotency_key?: string | null;
  metadata: Record<string, unknown>;
  refundable: boolean;
  created_at: string;
};

export type AdminCreditReservation = {
  id: string;
  user_id: string;
  task_type: string;
  status: string;
  reserved_credits: number;
  settled_credits?: number | null;
  idempotency_key: string;
  refundable: boolean;
  created_at: string;
  completed_at?: string | null;
};

export type AdminCreditAccountDetail = {
  account: AdminCreditAccount;
  reconciliation: {
    user_id: string;
    ledger_entries: number;
    opening_balance: number;
    ledger_balance: number;
    account_balance: number;
    matches: boolean;
  };
  ledger: AdminCreditLedgerEntry[];
  reservations: AdminCreditReservation[];
  settlements: Array<{ id: string; reservation_id: string; requested_actual_credits: number; settled_credits: number; adjustment: number; status: string; created_at: string }>;
  refunds: Array<{ id: string; reservation_id: string; credits: number; reason: string; created_at: string }>;
  rewards: Array<{ id: string; reward_type: string; credits: number; source: string; granted_by_user_id?: string | null; created_at: string }>;
};

export function getAdminCreditAccounts(search = "", limit = 50, offset = 0) {
  const query = new URLSearchParams({ search, limit: String(limit), offset: String(offset) });
  return requestStrict<{ accounts: AdminCreditAccount[]; total: number; limit: number; offset: number }>(`/admin/billing/accounts?${query.toString()}`);
}

export function getAdminCreditAccount(userId: string) {
  return requestStrict<AdminCreditAccountDetail>(`/admin/billing/accounts/${encodeURIComponent(userId)}`);
}

export function grantAdminCredits(userId: string, payload: { credits: number; reason: string; reference: string; idempotency_key: string }) {
  return requestStrict<{ grant: { id: string; credits: number; reason: string; reference: string; created_at: string }; credit_balance: number }>(`/admin/billing/accounts/${encodeURIComponent(userId)}/credits/grant`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refundAdminCreditReservation(reservationId: string, payload: { reason: string; reference: string }) {
  return requestStrict<{ refund: { reservation_id: string; credits: number; status: string }; credit_balance: number }>(`/admin/billing/reservations/${encodeURIComponent(reservationId)}/refund`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refundAdminCreditLedgerEntry(entryId: string, payload: { reason: string; reference: string }) {
  return requestStrict<{ refund: { ledger_entry_id: string; refund_ledger_entry_id: string; credits: number; reason: string; reference: string }; credit_balance: number }>(`/admin/billing/ledger/${encodeURIComponent(entryId)}/refund`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAgentConversations() {
  return requestStrict<{ conversations: AgentConversation[] }>("/api/agent/conversations");
}

export function getSecretary(locale: Locale) {
  return requestStrict<SecretaryState>(`/api/secretary?locale=${encodeURIComponent(locale)}`);
}

export function sendSecretaryMessage(content: string, locale: Locale, requestId: string) {
  return requestStrict<{ user_message: SecretaryMessage; assistant_message: SecretaryMessage; credits_used: number; credit_balance: number }>("/api/secretary/messages", {
    method: "POST",
    body: JSON.stringify({ content, locale, request_id: requestId })
  });
}

export function clearSecretaryMemory() {
  return requestStrict<{ ok: boolean }>("/api/secretary/memory", { method: "DELETE" });
}

export async function synthesizeSecretaryVoice(text: string, locale: Locale, signal?: AbortSignal) {
  const response = await fetch(`${API_URL}/api/secretary/voice`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, locale }),
    signal
  });
  if (!response.ok) {
    const error = new Error(await response.text()) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.blob();
}

export async function transcribeSecretaryAudio(audio: Blob, locale: Locale, signal?: AbortSignal) {
  const response = await fetch(`${API_URL}/api/secretary/transcribe?locale=${encodeURIComponent(locale)}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": audio.type || "audio/webm" },
    body: audio,
    signal
  });
  if (!response.ok) {
    const error = new Error(await response.text()) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<{ text: string; language: Locale }>;
}

export function createAgentConversation(title?: string) {
  return requestStrict<{ conversation: AgentConversation }>("/api/agent/conversations", { method: "POST", body: JSON.stringify({ title }) });
}

export function deleteAgentConversation(id: string) {
  return requestStrict<{ ok: boolean }>(`/api/agent/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteAllAgentConversations() {
  return requestStrict<{ ok: boolean; deleted: number }>("/api/agent/conversations", { method: "DELETE" });
}

export function getAgentConversation(id: string) {
  return requestStrict<{ conversation: AgentConversation; messages: AgentMessage[] }>(`/api/agent/conversations/${encodeURIComponent(id)}`);
}

export function getAgentQuota() {
  return requestStrict<{ plan: string; used: number; limit: number; remaining: number; concurrent_limit: number; running: number; credit_balance: number }>("/api/agent/quota");
}

export type AgentCapabilities = { plan: string; allowed_data_sources: string[]; agent_daily_runs: number; agent_concurrent_runs: number; queue_priority: number; credit_balance?: number };
export type AgentModelOption = { id: string; display_name: string; description: string; provider: string; available: boolean; reason?: "plan_required" | "unavailable" | null; credit_cost?: number | null };

export function getAgentCapabilities() {
  return requestStrict<{ capabilities: AgentCapabilities; models: AgentModelOption[]; skills: SkillSummary[]; quota: { plan: string; used: number; limit: number; remaining: number; concurrent_limit: number; running: number; credit_balance: number } }>("/api/agent/capabilities");
}

export type AgentQuoteResponse = CreditQuoteResponse & { task_type: string; planned_tools: string[]; plan: AgentRuntimePlan };
export function getAgentQuote(payload: { content: string; data_sources: string[]; skill_refs: SkillContextRef[]; custom_prompt: string; attachments: AgentAttachment[]; model: string }) {
  return requestStrict<AgentQuoteResponse>("/api/agent/quote", { method: "POST", body: JSON.stringify(payload) });
}

export function getSkillCatalog() {
  return requestStrict<{ skills: SkillSummary[] }>("/api/skills");
}

export function getSkillRuns(limit = 50) {
  return requestStrict<{ runs: Array<{ id: string; skill_id: string; agent_run_id?: string | null; trigger_source: string; status: string; credits_reserved: number; credits_used: number; evidence: Record<string, unknown>; usage: Record<string, unknown>; started_at: string; completed_at?: string | null }> }>(`/api/skills/runs?limit=${limit}`);
}

export function cancelAgentRun(runId: string) {
  return requestStrict<{ id: string; status: string }>(`/api/agent/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
}

export async function streamAgentMessage(
  conversationId: string,
  content: string,
  locale: Locale,
  signal: AbortSignal,
  onEvent: (event: AgentStreamEvent) => void,
  context?: Partial<AgentContext>
) {
  const response = await fetch(`${API_URL}/api/agent/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      content,
      locale,
      data_sources: context?.data_sources || [],
      skills: (context?.skills || []).filter((item): item is string => typeof item === "string"),
      skill_refs: context?.skill_refs || (context?.skills || []).filter((item): item is SkillContextRef => typeof item !== "string"),
      custom_prompt: context?.custom_prompt || "",
      attachments: context?.attachments || [],
      model: context?.model || "default"
    }),
    signal
  });
  if (!response.ok || !response.body) {
    const raw = await response.text();
    let message = raw || `Agent request failed (${response.status})`;
    try {
      const parsed = JSON.parse(raw) as { detail?: { message?: string } | string };
      message = typeof parsed.detail === "string" ? parsed.detail : parsed.detail?.message || message;
    } catch { /* Keep the server response when it is not JSON. */ }
    throw new Error(message);
  }
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
  return api<{ strategies: RuntimeStrategy[] }>("/strategies", { fallback: { strategies: [] }, locale });
}

export function getPlaybooks(locale: Locale = defaultLocale) {
  return api<{ playbooks: StrategyRow[]; reports: unknown[]; unavailable?: boolean }>("/playbooks", { fallback: fallbackPlaybooksForLocale(locale), locale });
}

export function getRuntimeStrategy(strategyId: string) {
  return requestStrict<{ strategy: RuntimeStrategy }>(`/strategies/${encodeURIComponent(strategyId)}`);
}

export function createRuntimeStrategy(draft: object, conversationId?: string) {
  return requestStrict<{ strategy: RuntimeStrategy }>("/strategies", { method: "POST", body: JSON.stringify({ draft, conversation_id: conversationId }), headers: { "Idempotency-Key": `web-strategy-${Date.now()}` } });
}

export function runNautilusBacktest(strategyId: string, engine: "mock" | "nautilus" = "mock") {
  return requestStrict<{ backtest: { id: string; result: Record<string, unknown> } }>(`/strategies/${encodeURIComponent(strategyId)}/backtest`, { method: "POST", body: JSON.stringify({ engine }) });
}

// ── Backtest Lab ─────────────────────────────────────

export type BacktestLabSpec = {
  name: string;
  mode: "daily" | "cross_sectional";
  signal: "momentum" | "mean_reversion" | "breakout" | "relative_strength";
  assets: string[];
  fast_window: number;
  slow_window: number;
  entry_threshold: number;
  exit_threshold: number;
  rebalance_days: number;
  long_short: boolean;
  max_position: number;
  fee_bps: number;
  stop_loss_pct: number | null;
  thesis: string;
};

export type BacktestLabRun = {
  id: string;
  status: string;
  engine?: string;
  mode: string;
  spec: BacktestLabSpec;
  run_spec?: Record<string, unknown>;
  symbols: string[];
  window: { start: string | null; end: string | null };
  performance: Record<string, number> & { per_asset?: Record<string, Record<string, number>> };
  equity_curve: Array<{ ts: string; equity: number }>;
  drawdown_curve?: Array<{ ts: string; drawdown: number }>;
  benchmark_curve?: Array<{ ts: string; equity: number }>;
  trades?: Array<Record<string, unknown>>;
  positions?: Array<Record<string, unknown>>;
  charts?: {
    equity?: { data: unknown[]; layout?: Record<string, unknown> };
    drawdown?: { data: unknown[]; layout?: Record<string, unknown> };
    benchmark_comparison?: { data: unknown[]; layout?: Record<string, unknown> };
    trades?: { data: unknown[]; layout?: Record<string, unknown> };
    positions?: { data: unknown[]; layout?: Record<string, unknown> };
  };
  assumptions: Record<string, unknown>;
  context_used: Record<string, unknown>;
  credits_spent: number;
  credits_reserved?: number;
  created_at: string;
  is_legacy?: boolean;
};

export type BacktestLabStatus = {
  symbols: string[];
  coverage: Record<string, { bars: number; first_ts: string | null; last_ts: string | null }>;
};

export function getBacktestLabStatus() {
  return requestStrict<BacktestLabStatus>("/backtest-lab/status");
}

export function generateBacktestLabSpec(idea: string, useMemory: boolean, locale: string) {
  return requestStrict<{ spec: BacktestLabSpec; meta: { fallback: boolean; context_notes: number } }>("/backtest-lab/generate-spec", {
    method: "POST",
    body: JSON.stringify({ idea, use_memory: useMemory, locale })
  });
}

export function runBacktestLab(spec: BacktestLabSpec, windowDays: number, contextMeta: Record<string, unknown> = {}) {
  return requestStrict<{ run: BacktestLabRun }>("/backtest-lab/runs", {
    method: "POST",
    body: JSON.stringify({ spec, window_days: windowDays, context_meta: contextMeta })
  });
}

export function getBacktestLabRuns(limit = 20) {
  return requestStrict<{ runs: BacktestLabRun[] }>(`/backtest-lab/runs?limit=${limit}`);
}

export function refreshBacktestLabData() {
  return requestStrict<BacktestLabStatus & { stats: Record<string, { fetched: number; upserted: number }> }>("/backtest-lab/data/refresh", { method: "POST" });
}

export function exportBacktestLabRun(runId: string, format: "json" | "csv" = "json") {
  return requestStrict<{ artifact: { id: string; format: string; credits_spent: number; relative_path: string; size_bytes: number } }>(`/backtest-lab/runs/${encodeURIComponent(runId)}/export?format=${format}`, { method: "POST" });
}

export function previewStrategyActivation(strategyId: string, mode: "PAPER" | "SHADOW", accountId?: string) {
  return requestStrict<{ intent: { id: string; strategy_version: number; execution_mode: string; expires_at: string; confirmation: string; payload: { preview?: ActivationPreviewSummary; [key: string]: unknown } } }>(`/strategies/${encodeURIComponent(strategyId)}/preview-activation`, { method: "POST", body: JSON.stringify({ mode, account_id: accountId }), headers: { "Idempotency-Key": `web-activation-${strategyId}-${mode}-${Date.now()}` } });
}

export function confirmStrategyActivation(strategyId: string, intentId: string, confirmation: string) {
  return requestStrict<{ activation: Record<string, unknown>; run: RuntimeRun }>(`/strategies/${encodeURIComponent(strategyId)}/activate`, { method: "POST", body: JSON.stringify({ intent_id: intentId, confirmation }) });
}

export function controlStrategy(strategyId: string, action: "pause" | "resume" | "stop") {
  return requestStrict<{ run: RuntimeRun }>(`/strategies/${encodeURIComponent(strategyId)}/${action}`, { method: "POST" });
}

export function getTradingRuntimeHealth() {
  return requestStrict<TradingRuntimeHealth>("/trading/runtime/health");
}

export type TradingRuntimeHealth = {
  status: string;
  service: string;
  adapter: RuntimeAdapterHealth;
  adapters: RuntimeAdapterHealth[];
  marketData: {
    enabled: boolean;
    providers: RuntimeMarketProviderStatus[];
    quotes: number;
  };
  nautilus: {
    available: boolean;
    version: string | null;
    messageBus: boolean;
    error: string | null;
    platform: string;
    machine: string;
    python: string;
  };
  nautilusInstalled: boolean;
  modes: string[];
  liveTrading: boolean;
  withdrawal: boolean;
  transfer: boolean;
  killSwitch: boolean;
  recoveredOrders: number;
  runs: number;
};

export type RuntimeMarketProviderStatus = {
  provider: string;
  status: string;
  lastSuccessAt: string | null;
  failures: number;
  lastError: string | null;
  circuitOpen: boolean;
  liveOrders: false;
};

export type RuntimeMarketQuote = {
  asset: string;
  symbol: string;
  price: number;
  provider: string;
  timestamp: string;
  stale: boolean;
};

export type RuntimeEvent = {
  id: number;
  event_type: string;
  aggregate_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type RuntimeAdapterHealth = {
  adapter: string;
  status: string;
  configured?: boolean;
  live: boolean;
  orders?: boolean;
  withdrawal?: boolean;
  transfer?: boolean;
};

export function getTradingAccounts() {
  return requestStrict<{ accounts: TradingAccount[] }>("/trading/accounts");
}

export function getTradingRuntimeMarket(refresh = false, symbols: string[] = []) {
  const params = new URLSearchParams({ refresh: String(refresh) });
  symbols.forEach((symbol) => params.append("symbols", symbol));
  return requestStrict<{ status: string; quotes: RuntimeMarketQuote[]; providers: RuntimeMarketProviderStatus[]; signals?: Record<string, unknown>[]; orders?: Record<string, unknown>[]; liveOrders: false }>(`/trading/runtime/market?${params.toString()}`);
}

export function getTradingRuntimeEvents(limit = 30) {
  return requestStrict<{ events: RuntimeEvent[] }>(`/trading/runtime/events?limit=${limit}`);
}

export function getTradingPositions() {
  return requestStrict<{ positions: TradingPosition[] }>("/trading/positions");
}

export function getTradingPerformance() {
  return requestStrict<{ accounts: TradingPerformance[] }>("/trading/performance");
}

export function getTradingOrders() {
  return requestStrict<{ orders: TradingOrder[] }>("/trading/orders");
}

export function syncTradingRuntime(accountId: string) {
  return requestStrict<{ sync: { account_id: string; snapshots: number; orders: number; signals: number } }>("/trading/runtime/sync", {
    method: "POST",
    body: JSON.stringify({ account_id: accountId })
  });
}

export function getOptionChain(currency: "BTC" | "ETH" = "BTC") {
  return api<{ provider: string; status: string; currency: string; fetched_at?: string; source_url?: string; instruments: OptionInstrument[]; error?: string; live_trading: false }>(`/options/chain?currency=${currency}`, {
    fallback: { provider: "deribit_public", status: "DEGRADED", currency, instruments: [], error: "Sign in and configure API access to load the option chain.", live_trading: false }
  });
}

export function getLongGammaCandidates(currency: "BTC" | "ETH" = "BTC") {
  return api<{ provider: string; status: string; currency: string; fetched_at?: string; source_url?: string; instrument_count: number; candidates: LongGammaCandidate[]; error?: string; live_trading: false }>(`/options/long-gamma?currency=${currency}`, {
    fallback: { provider: "deribit_public", status: "DEGRADED", currency, instrument_count: 0, candidates: [], error: "Deribit public options data is currently unavailable.", live_trading: false }
  });
}

export function getEarningsGamma(locale: Locale = defaultLocale) {
  const language = locale === "zh" ? "zh" : "en";
  return api<{ status: string; source: string; candidates: EarningsGammaCandidate[]; live_trading: false }>(`/options/earnings-gamma?language=${language}`, {
    fallback: { status: "DEGRADED", source: "earnings_research", candidates: [], live_trading: false }
  });
}

export type OptionSurfaceRow = {
  x: number;
  y: number;
  z: number;
  strike: number;
  expiry: string;
  instrument: string;
  open_interest: number;
  volume_24h: number;
  option_type: "call" | "put";
};

export type OptionSurfaceResponse = {
  status: string;
  provider: string;
  currency: string;
  fetched_at?: string;
  surface: {
    x: number[];
    y: number[];
    z: number[];
    type: "mark_iv" | "mark_price" | "gamma" | "theta" | "vega" | "spread_pct";
    underlying_price: number;
    rows: OptionSurfaceRow[];
  };
  candidates: LongGammaCandidate[];
  insights: { atm_iv: number | null; dte: number | null; strike: number | null; put25_iv: number | null; call25_iv: number | null; skew_pct: number | null; underlying_price: number } | null;
  error?: string;
  live_trading: false;
};

const emptyOptionSurface: OptionSurfaceResponse = {
  status: "DEGRADED",
  provider: "unavailable",
  currency: "BTC",
  surface: { x: [], y: [], z: [], type: "mark_iv", underlying_price: 0, rows: [] },
  candidates: [],
  insights: null,
  error: "Option surface data is currently unavailable.",
  live_trading: false,
};

export function getOptionsSurface(currency: string, type: string = "mark_iv") {
  return api<OptionSurfaceResponse>(`/options/surface?currency=${encodeURIComponent(currency)}&type=${encodeURIComponent(type)}`, {
    fallback: { ...emptyOptionSurface, currency }
  });
}

export function getOptionsSurfaceTickers(locale: Locale = defaultLocale) {
  return api<{ tickers: { symbol: string; provider: string; label: string; market_cap: string }[]; unavailable?: boolean }>("/options/surface-tickers", {
    fallback: { tickers: [], unavailable: true }
  });
}


export function getDailyPushPreferences(locale: Locale = defaultLocale) {
  return api<{ preference: DailyPushPreference; history: DeliveryRecord[] }>(`/notifications/preferences/daily-brief`, {
    fallback: { preference: { enabled: false, timezone: "UTC", local_time: "08:30", channel: "email", locale, include_portfolio: true, include_market: true, include_signals: false, include_risk: true, include_sentiment: false, quiet_hours: {}, max_length: 200, next_delivery_at: null, recipient: null, recipient_verified_at: null }, history: [] },
    locale,
    headers: { "X-PG-Locale": locale },
  });
}

export function updateDailyPushPreferences(preference: Partial<DailyPushPreference>) {
  return requestStrict<{ preference: DailyPushPreference }>("/notifications/preferences/daily-brief", { method: "PUT", body: JSON.stringify(preference) });
}

export function sendDailyPushTest(channel: DailyPushPreference["channel"], locale: Locale = defaultLocale) {
  const message = locale === "zh" ? "PureGamma AI 每日简报测试。使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。" : "PureGamma AI daily brief test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.";
  return requestStrict<{ delivery: DeliveryRecord }>("/notifications/send", { method: "POST", body: JSON.stringify({ channel, message, locale, metadata: { idempotency_key: `daily-push-test-${Date.now()}` } }) });
}

export type IMessageConfig = { official_number: string; provider: string; enabled_plans: string[]; recipient: string | null; recipient_verified_at: string | null };

export function getIMessageConfig() {
  return requestStrict<IMessageConfig>("/notifications/imessage/config");
}

export function requestIMessageVerification(recipient: string) {
  return requestStrict<{ challenge_id: string; expires_at: string; recipient: string; development_code?: string }>("/notifications/imessage/verify/request", { method: "POST", body: JSON.stringify({ recipient }) });
}

export function confirmIMessageVerification(challenge_id: string, code: string) {
  return requestStrict<{ recipient: string; recipient_verified_at: string }>("/notifications/imessage/verify/confirm", { method: "POST", body: JSON.stringify({ challenge_id, code }) });
}

export function getBillingSubscription(locale: Locale = defaultLocale) {
  return api<SubscriptionState>(`/billing/subscription?locale=${locale}`, { fallback: fallbackSubscription, locale });
}

export function getBillingCredits(locale: Locale = defaultLocale) {
  return api<{ credit_balance: number; usage_history: { id: string; action: string; credits_delta: number; balance_after: number; created_at: string }[] }>(`/billing/credits?locale=${locale}`, { fallback: { credit_balance: 0, usage_history: [] }, locale });
}

export type CreditBudget = {
  automation_key: string;
  daily_limit: number;
  monthly_limit: number;
  per_run_limit: number;
  daily_used: number;
  monthly_used: number;
  next_estimated_credits: number | null;
  alert_threshold_pct: number;
  enabled: boolean;
  paused: boolean;
  pause_reason?: string | null;
};

export type CreditReward = {
  id: string;
  reward_type: string;
  credits: number;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export function getBillingBudget(locale: Locale = defaultLocale) {
  return api<{ budgets: CreditBudget[]; unavailable?: boolean }>("/billing/budget", { fallback: { budgets: [], unavailable: true }, locale });
}

export function getBillingRewards(locale: Locale = defaultLocale) {
  return api<{ rewards: CreditReward[]; unavailable?: boolean }>("/billing/rewards", { fallback: { rewards: [], unavailable: true }, locale });
}

export type CreditQuoteResponse = { estimated_min: number; estimated_max: number; reservation_amount: number; pricing_version: string; unavailable?: boolean };
export function getCreditQuote(payload: { task_type: string; requested_model: string; resolved_model?: string; input_tokens?: number; attachment_bytes?: number; tool_calls?: string[]; selected_data_sources?: string[] }, locale: Locale = defaultLocale) {
  return api<CreditQuoteResponse>("/billing/quote", { method: "POST", body: JSON.stringify(payload), fallback: { estimated_min: 0, estimated_max: 0, reservation_amount: 0, pricing_version: "unavailable", unavailable: true }, locale });
}

export function createCheckoutSession(plan_name: string, locale: Locale = defaultLocale) {
  return post<CheckoutResponse | null>("/billing/create-checkout-session", { plan_name, locale }, null, locale);
}

export function createPaymentLinkCheckout(plan_name: string, locale: Locale = defaultLocale) {
  return post<CheckoutResponse | null>("/billing/create-payment-link-checkout", { plan_name, locale }, null, locale);
}

export function createBillingCheckout(plan_name: string, checkoutMode: "session" | "payment_link", locale: Locale = defaultLocale) {
  return checkoutMode === "payment_link" ? createPaymentLinkCheckout(plan_name, locale) : createCheckoutSession(plan_name, locale);
}

export function createPortalSession(locale: Locale = defaultLocale) {
  return post("/billing/create-portal-session", { locale }, { portal_url: "", mode: "unavailable" }, locale);
}

export function cancelSubscription(locale: Locale = defaultLocale) {
  return post<SubscriptionState>("/billing/cancel-subscription", { locale }, fallbackSubscription, locale);
}

export function reactivateSubscription(locale: Locale = defaultLocale) {
  return post<SubscriptionState>("/billing/reactivate-subscription", { locale }, fallbackSubscription, locale);
}
