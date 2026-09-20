import { Context, Service } from '@deepseek-ai/cordis'

export type TradeSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit' | 'stop' | 'stop-limit'
export type TimeInForce = 'GTC' | 'IOC' | 'FOK' | 'DAY'
export type OrderStatus =
  | 'previewed'
  | 'pending-submit'
  | 'open'
  | 'partially-filled'
  | 'filled'
  | 'cancel-pending'
  | 'cancelled'
  | 'rejected'
  | 'unknown'

export interface OrderIntent {
  clientOrderId: string
  accountId: string
  venue: string
  instrument: string
  side: TradeSide
  type: OrderType
  quantity: string
  limitPrice?: string
  stopPrice?: string
  timeInForce?: TimeInForce
  reduceOnly: boolean
  strategyId?: string
  mandateId?: string
  createdAt: string
}

export interface RiskCheck {
  name: string
  passed: boolean
  observedValue?: string
  limitValue?: string
  reason?: string
}

export interface TradePreview {
  previewId: string
  intentHash: string
  intent: OrderIntent
  allowed: boolean
  checks: readonly RiskCheck[]
  expiresAt: string
  createdAt: string
}

export interface OrderFill {
  fillId: string
  quantity: string
  price: string
  fee?: string
  feeCurrency?: string
  observedAt: string
}

export interface ExecutionOrder {
  clientOrderId: string
  brokerOrderId?: string
  status: OrderStatus
  intent: OrderIntent
  filledQuantity: string
  averageFillPrice?: string
  fills: readonly OrderFill[]
  submittedAt?: string
  updatedAt: string
  rejectionReason?: string
}

export interface ExecutionSafetyStatus {
  enabled: boolean
  killSwitchEngaged: boolean
  reconciliationHealthy: boolean
  ownershipVerified: boolean
  brokerHealthy: boolean
  approvalRequired: boolean
  reason?: string
  observedAt: string
}

export interface ReconciliationResult {
  healthy: boolean
  checkedAt: string
  discrepancies: readonly {
    accountId: string
    kind: 'cash' | 'position' | 'order' | 'ledger'
    detail: string
  }[]
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgTrading: TradingService
  }
}

/**
 * Guarded execution seam.
 *
 * Implementations MUST preserve these invariants:
 * - `clientOrderId` is the idempotency key across restart/retry boundaries.
 * - submit timeout/ambiguous transport state becomes `unknown`; never blind retry.
 * - `queryByClientOrderId` can recover open AND terminal/filled orders.
 * - reduce-only is enforced three ways: deterministic pre-trade validation,
 *   provider/venue request mapping, and post-submit/reconciliation ownership checks.
 * - kill switch blocks new exposure while query/cancel/fill/reconciliation stay live.
 * - all monetary/quantity values cross this seam as decimal strings, never JS floats.
 */
export abstract class TradingService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgTrading')
  }

  abstract safety(accountId?: string): Promise<ExecutionSafetyStatus>
  abstract preview(intent: OrderIntent): Promise<TradePreview>
  abstract submit(input: {
    previewId: string
    expectedIntentHash: string
    intent: OrderIntent
  }): Promise<ExecutionOrder>
  abstract queryByClientOrderId(clientOrderId: string): Promise<ExecutionOrder | undefined>
  abstract cancel(clientOrderId: string): Promise<ExecutionOrder>
  abstract reconcile(accountId?: string): Promise<ReconciliationResult>
}

export default TradingService
