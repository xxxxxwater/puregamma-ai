import type { Context } from '@deepseek-ai/cordis'
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
  authTokenEnv?: string
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
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
  const timestamp = Date.parse(raw)
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
  private readonly timeoutMs: number

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 10000
  }

  private async requestPortfolio(): Promise<LegacyPortfolioPayload> {
    const token = process.env[this.tokenEnv]
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
    const selected = accountIds === undefined ? undefined : new Set(accountIds)

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
        stale: globalStale || status?.toUpperCase() === 'STALE',
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
      const observedAt = isoValue(raw.as_of) ?? globalObservedAt
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
        stale: globalStale || status?.toUpperCase() === 'STALE',
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
        stale: globalStale || account?.stale === true,
      }]
    })

    const connected = payload.connected === true && accounts.length > 0
    const totalNav = connected ? decimalValue(payload.nav) ?? null : null
    const totalCash = connected ? decimalValue(payload.available_cash) ?? null : null
    let positionsValue = connected ? sumHoldingValues(payload.holdings) ?? null : null
    if (positionsValue === null && totalNav !== null && totalCash !== null) {
      const derived = Number(totalNav) - Number(totalCash)
      if (Number.isFinite(derived)) positionsValue = String(derived)
    }

    const nav: PortfolioNavSnapshot = {
      currency: 'USD',
      nav: totalNav,
      cash: totalCash,
      positionsValue,
      calculatedAt: globalObservedAt,
      priceObservedAt: globalObservedAt,
      calculationVersion: 'compatibility-portfolio-v1',
      stale: globalStale,
      ...connected ? {} : { reason: 'no connected portfolio snapshot' },
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
