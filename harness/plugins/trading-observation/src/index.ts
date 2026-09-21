import { Context, Service } from '@deepseek-ai/cordis'

/**
 * Live-trading observations are deliberately NOT the consolidated Portfolio/NAV
 * read model, a strategy command surface, or permission to trade. No provider is
 * installed by defining this contract. The provider MUST resolve the real
 * authenticated end-user and account entitlement server-side for EVERY call;
 * the public arguments below are selectors, never identity or approval proof.
 */
export type Observation<T> =
  | { state: 'available' | 'stale'; accountId: string; source: string; observedAt: string; data: T; reason?: string }
  | { state: 'unavailable'; source: string; observedAt: string; reason: string; accountId?: never; data?: never }

export interface TradingPosition {
  accountId: string
  venue: string
  instrument: string
  side: 'long' | 'short' | 'flat'
  /** Signed/absolute venue quantity and prices remain decimal strings. */
  quantity: string
  entryPrice?: string
  markPrice?: string
  unrealizedPnl?: string
  initialMargin?: string
  maintenanceMargin?: string
  leverage?: string
  ownership: 'strategy' | 'manual' | 'external' | 'unknown'
  strategyId?: string
  observedAt: string
}

export interface TradingOrderFill {
  fillId: string
  quantity: string
  price: string
  fee?: string
  feeCurrency?: string
  observedAt: string
}

export type ObservedOrderStatus = 'pending-submit' | 'open' | 'partially-filled' | 'filled' | 'cancel-pending' | 'cancelled' | 'rejected' | 'unknown'

export interface TradingObservedOrder {
  accountId: string
  venue: string
  instrument: string
  clientOrderId: string
  venueOrderId?: string
  status: ObservedOrderStatus
  side: 'buy' | 'sell'
  type: string
  reduceOnly?: boolean
  originalQuantity: string
  filledQuantity: string
  limitPrice?: string
  stopPrice?: string
  averageFillPrice?: string
  fills: readonly TradingOrderFill[]
  ownership: 'strategy' | 'manual' | 'external' | 'unknown'
  strategyId?: string
  submittedAt?: string
  observedAt: string
}

export interface TradingPositionsSnapshot {
  positions: readonly TradingPosition[]
  /** True only when the provider verified a complete, fresh venue account view. */
  complete: boolean
  cursor?: string
}

export interface TradingOrdersSnapshot {
  orders: readonly TradingObservedOrder[]
  /** Historical terminal orders MUST remain addressable by clientOrderId. */
  nextCursor?: string
  complete: boolean
}

/** This is observed evidence only; it is NEVER an execution authorization. */
export interface TradingSafetyObservation {
  brokerConnected?: boolean
  reconciliationHealthy?: boolean
  protectionVerified?: boolean
  ownershipVerified?: boolean
  killSwitchEngaged?: boolean
  leaseHealthy?: boolean
  blockingGates: readonly string[]
  lastReconciledAt?: string
  lastError?: string
}

declare module '@deepseek-ai/cordis' {
  interface Context { pgTradingObservation: TradingObservationService }
}

/**
 * Provider requirements before installation:
 * - authenticate each requesting user and enforce per-account read entitlements
 *   on positions, order lists, client-ID lookup and safety; do not accept a
 *   client-supplied user ID, bearer service credential or account selector as
 *   authorization. No session principal => unavailable/deny, not a shared view.
 * - reconcile venue and journal; preserve manual/external ownership; include
 *   pending, UNKNOWN, partial, filled and terminal orders and real fill/fees.
 * - failure or missing provider data => unavailable/stale, NEVER [] or healthy.
 * - enforce bounded pagination/limit and stable, account-scoped cursors.
 * - query methods cannot submit/cancel, change mandates, enable live trading,
 *   approve an intent, flip kill switches or reload strategies.
 */
export abstract class TradingObservationService extends Service {
  constructor(ctx: Context) { super(ctx, 'pgTradingObservation') }
  abstract positions(accountId: string): Promise<Observation<TradingPositionsSnapshot>>
  abstract orders(accountId: string, options?: { cursor?: string; limit?: number }): Promise<Observation<TradingOrdersSnapshot>>
  abstract orderByClientOrderId(accountId: string, clientOrderId: string): Promise<Observation<TradingObservedOrder | null>>
  abstract safety(accountId: string): Promise<Observation<TradingSafetyObservation>>
}

export default TradingObservationService
