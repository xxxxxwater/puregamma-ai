import { Context, Service } from '@deepseek-ai/cordis'

export interface PortfolioAccountRef {
  id: string
  provider: string
  label?: string
  baseCurrency: string
}

export interface PortfolioPosition {
  accountId: string
  instrument: string
  quantity: string
  marketValue?: string
  currency: string
  averageCost?: string
  unrealizedPnl?: string
  observedAt: string
  source: string
  stale: boolean
}

export interface PortfolioCashBalance {
  accountId: string
  currency: string
  available: string
  total: string
  observedAt: string
  source: string
  stale: boolean
}

export interface PortfolioNavSnapshot {
  currency: string
  nav: string | null
  cash: string | null
  positionsValue: string | null
  calculatedAt: string
  priceObservedAt?: string
  calculationVersion: string
  stale: boolean
  reason?: string
}

export interface PortfolioSnapshot {
  accounts: readonly PortfolioAccountRef[]
  positions: readonly PortfolioPosition[]
  cash: readonly PortfolioCashBalance[]
  nav: PortfolioNavSnapshot
  observedAt: string
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgPortfolio: PortfolioService
  }
}

/**
 * Consolidated portfolio/NAV seam. Provider-specific credentials and APIs stay
 * behind implementations; read consumers receive explicit freshness metadata.
 */
export abstract class PortfolioService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgPortfolio')
  }

  abstract snapshot(options?: { accountIds?: readonly string[]; refresh?: boolean }): Promise<PortfolioSnapshot>
  abstract accounts(): Promise<readonly PortfolioAccountRef[]>
  abstract positions(accountIds?: readonly string[]): Promise<readonly PortfolioPosition[]>
  abstract nav(options?: { accountIds?: readonly string[]; refresh?: boolean }): Promise<PortfolioNavSnapshot>
}

export default PortfolioService
