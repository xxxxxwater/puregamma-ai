import type { Context } from '@deepseek-ai/cordis'
import { createBearerSource, type BearerSource } from '@puregamma/dsh-legacy-auth'
import z from '@deepseek-ai/schemastery'
import PortfolioService, {
  type PortfolioAccountRef,
  type PortfolioCashBalance,
  type PortfolioNavSnapshot,
  type PortfolioPosition,
  type PortfolioSnapshot,
} from '@puregamma/dsh-portfolio'

export interface Config {
  baseUrl?: string
  authTokenEnv?: string; authTokenFile?: string; authTokenCacheMs?: number
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  // Multi-tenant Hosts: a per-user token file the session broker rotates; never falls back to the env token.
  authTokenFile: z.string(),
  authTokenCacheMs: z.number().min(0).max(60000).default(5000),
  requestTimeoutMs: z.number().min(100).max(60000).default(10000),
})

interface LegacyAccount {
  id?: unknown
  provider?: unknown
  name?: unknown
  status?: unknown
  nav?: unknown
  available_cash?: unknown
  as_of?: unknown
}

interface LegacyPosition {
  symbol?: unknown
  venue?: unknown
  side?: unknown
  quantity?: unknown
  mark_price?: unknown
  unrealized_pnl?: unknown
}

interface LegacyHolding {
  value?: unknown
}

interface LegacyPortfolioPayload {
  connected?: unknown
  stale?: unknown
  data_as_of?: unknown
  nav?: unknown
  available_cash?: unknown
  positions?: unknown
  holdings?: unknown
  accounts?: unknown
}

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function stringValue(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim().length > 0) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function decimalValue(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'string' && value.trim().length > 0 && Number.isFinite(Number(value))) return value.trim()
  return undefined
}

function isoValue(value: unknown): string | undefined {
  const raw = stringValue(value)
  if (raw === undefined) return undefined
  // The legacy API stores UTC; an offset-less date-time (SQLite) must not be
  // re-read in the Host's local zone.
  const timestamp = Date.parse(/T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(raw) ? `${raw}Z` : raw)
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : undefined
}

function positionSide(value: unknown): PortfolioPosition['side'] {
  switch (String(value ?? '').trim().toLowerCase()) {
    case 'long': return 'long'
    case 'short': return 'short'
    case 'flat': return 'flat'
    default: return undefined
  }
}

function sumHoldingValues(value: unknown): string | undefined {
  if (!Array.isArray(value)) return undefined
  let total = 0
  let seen = false
  for (const raw of value as LegacyHolding[]) {
    const item = decimalValue(raw.value)
    if (item === undefined) continue
    total += Number(item)
    seen = true
  }
  return seen && Number.isFinite(total) ? String(total) : undefined
}

function accountStale(status: string | undefined, globalStale: boolean): boolean {
  return status === undefined ? globalStale : status.toUpperCase() === 'STALE'
}

function sumDecimals(values: readonly unknown[]): string | undefined {
  let total = 0
  for (const value of values) {
    const item = decimalValue(value)
    if (item === undefined) return undefined
    total += Number(item)
  }
  return values.length > 0 && Number.isFinite(total) ? String(total) : undefined
}

/**
 * Migration-only authenticated portfolio provider. The old FastAPI endpoint is
 * treated as a compatibility transport; Harness owns the durable contract and
 * model-facing surface. This package is deleted once native Plaid/IBKR/
 * Hyperliquid/EVM providers expose the same pgPortfolio seam directly.
 */
export class LegacyApiPortfolioProvider extends PortfolioService {
  static Config = Config

  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly bearer: BearerSource
  private readonly timeoutMs: number

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.bearer = createBearerSource(config)
    this.tokenEnv = this.bearer.description
    this.timeoutMs = config.requestTimeoutMs ?? 10000
  }

  private async requestPortfolio(): Promise<LegacyPortfolioPayload> {
    const token = this.bearer()
    if (token === undefined || token.length === 0) {
      throw new Error(`PureGamma Harness portfolio compatibility provider requires bearer token in ${this.tokenEnv}`)
    }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(`${this.baseUrl}/portfolio`, {
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${token}`,
        },
      })
      if (!response.ok) {
        throw new Error(`portfolio compatibility API returned HTTP ${response.status}`)
      }
      const payload = await response.json()
      if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
        throw new Error('portfolio compatibility API returned a non-object payload')
      }
      return payload as LegacyPortfolioPayload
    } finally {
      clearTimeout(timer)
    }
  }

  private normalize(payload: LegacyPortfolioPayload, accountIds?: readonly string[]): PortfolioSnapshot {
    const now = new Date().toISOString()
    const globalObservedAt = isoValue(payload.data_as_of) ?? now
    const globalStale = payload.stale === true
    // An empty filter means every connected account (the tools pass [] for "all").
    const selected = accountIds === undefined || accountIds.length === 0 ? undefined : new Set(accountIds)

    const legacyAccounts = Array.isArray(payload.accounts) ? payload.accounts as LegacyAccount[] : []
    const accounts: PortfolioAccountRef[] = legacyAccounts.flatMap((raw): PortfolioAccountRef[] => {
      const id = stringValue(raw.id)
      const provider = stringValue(raw.provider)
      if (id === undefined || provider === undefined || (selected !== undefined && !selected.has(id))) return []
      const observedAt = isoValue(raw.as_of)
      const status = stringValue(raw.status)
      return [{
        id,
        provider: provider.toLowerCase(),
        label: stringValue(raw.name),
        baseCurrency: 'USD',
        status,
        observedAt,
        // Legacy reports each account's effective status (STALE past its own
        // venue window); the payload-level flag is "any account is stale".
        stale: accountStale(status, globalStale),
      }]
    })

    const accountByProvider = new Map<string, PortfolioAccountRef[]>()
    for (const account of accounts) {
      const group = accountByProvider.get(account.provider) ?? []
      group.push(account)
      accountByProvider.set(account.provider, group)
    }

    const cash: PortfolioCashBalance[] = legacyAccounts.flatMap((raw): PortfolioCashBalance[] => {
      const id = stringValue(raw.id)
      const provider = stringValue(raw.provider)?.toLowerCase()
      const available = decimalValue(raw.available_cash)
      if (id === undefined || provider === undefined || available === undefined) return []
      if (selected !== undefined && !selected.has(id)) return []
      // The legacy endpoint reports 0.0 cash (and NAV) for an account that has
      // no snapshot yet; that is "unknown", not a zero balance.
      const observedAt = isoValue(raw.as_of)
      if (observedAt === undefined) return []
      const status = stringValue(raw.status)
      return [{
        accountId: id,
        currency: 'USD',
        available,
        // The compatibility endpoint exposes available cash only. Do not
        // invent an unavailable total-cash concept; mirror the known balance.
        total: available,
        observedAt,
        source: `compatibility:${provider}`,
        stale: accountStale(status, globalStale),
      }]
    })

    const legacyPositions = Array.isArray(payload.positions) ? payload.positions as LegacyPosition[] : []
    const positions: PortfolioPosition[] = legacyPositions.flatMap((raw): PortfolioPosition[] => {
      const instrument = stringValue(raw.symbol)
      const provider = stringValue(raw.venue)?.toLowerCase()
      const quantity = decimalValue(raw.quantity)
      if (instrument === undefined || provider === undefined || quantity === undefined) return []
      const candidates = accountByProvider.get(provider) ?? []
      if (selected !== undefined && candidates.length === 0) return []
      const account = candidates.length === 1 ? candidates[0] : undefined
      const observedAt = account?.observedAt ?? globalObservedAt
      return [{
        ...(account === undefined ? {} : { accountId: account.id }),
        instrument,
        side: positionSide(raw.side),
        quantity,
        markPrice: decimalValue(raw.mark_price),
        currency: 'USD',
        unrealizedPnl: decimalValue(raw.unrealized_pnl),
        observedAt,
        source: `compatibility:${provider}`,
        stale: account === undefined ? globalStale : account.stale === true,
      }]
    })

    // Accounts with a snapshot carry a real figure; the rest are unknown.
    const measured = legacyAccounts.filter(raw => {
      const id = stringValue(raw.id)
      return id !== undefined && stringValue(raw.provider) !== undefined && isoValue(raw.as_of) !== undefined && (selected === undefined || selected.has(id))
    })
    const unmeasured = accounts.length - measured.length
    const connected = payload.connected === true && measured.length > 0
    let totalNav: string | null
    let totalCash: string | null
    let positionsValue: string | null
    let navObservedAt = globalObservedAt
    let navStale = globalStale
    if (selected === undefined) {
      totalNav = connected ? decimalValue(payload.nav) ?? null : null
      totalCash = connected ? decimalValue(payload.available_cash) ?? null : null
      positionsValue = connected ? sumHoldingValues(payload.holdings) ?? null : null
    } else {
      // A filtered read sums only the selected accounts' own figures; the
      // payload's totals cover every account and would overstate the subset.
      totalNav = connected ? sumDecimals(measured.map(raw => raw.nav)) ?? null : null
      totalCash = connected ? sumDecimals(measured.map(raw => raw.available_cash)) ?? null : null
      positionsValue = null
      const times = measured.map(raw => Date.parse(isoValue(raw.as_of)!))
      if (times.length > 0) navObservedAt = new Date(Math.min(...times)).toISOString()
      navStale = accounts.some(account => account.stale === true)
    }
    if (positionsValue === null && totalNav !== null && totalCash !== null) {
      const derived = Number(totalNav) - Number(totalCash)
      if (Number.isFinite(derived)) positionsValue = String(derived)
    }
    const reason = !connected
      ? 'no connected portfolio snapshot'
      : unmeasured > 0
        ? `NAV excludes ${unmeasured} connected account${unmeasured === 1 ? '' : 's'} without a snapshot`
        : undefined

    const nav: PortfolioNavSnapshot = {
      currency: 'USD',
      nav: totalNav,
      cash: totalCash,
      positionsValue,
      calculatedAt: navObservedAt,
      priceObservedAt: navObservedAt,
      calculationVersion: 'compatibility-portfolio-v1',
      stale: navStale,
      ...reason === undefined ? {} : { reason },
    }

    return {
      accounts,
      positions,
      cash,
      nav,
      observedAt: globalObservedAt,
    }
  }

  async snapshot(options: { accountIds?: readonly string[]; refresh?: boolean } = {}): Promise<PortfolioSnapshot> {
    // `refresh` intentionally does not fan out to billable/vendor sync calls in
    // this compatibility provider. It reads the latest server-authoritative
    // snapshot; native providers will own explicit refresh semantics.
    const payload = await this.requestPortfolio()
    return this.normalize(payload, options.accountIds)
  }

  async accounts(): Promise<readonly PortfolioAccountRef[]> {
    return (await this.snapshot()).accounts
  }

  async positions(accountIds?: readonly string[]): Promise<readonly PortfolioPosition[]> {
    return (await this.snapshot({ accountIds })).positions
  }

  async nav(options: { accountIds?: readonly string[]; refresh?: boolean } = {}): Promise<PortfolioNavSnapshot> {
    return (await this.snapshot(options)).nav
  }
}

export default LegacyApiPortfolioProvider
