import { Context, Service } from '@deepseek-ai/cordis'
import type { ExecutionEligibility, ExecutionEligibilityInput, ExecutionMandate, IndependentApproval } from './policy.ts'
export { canonicalPositiveDecimal, decimalWithin, evaluateExecutionEligibility } from './policy.ts'
export type { ExecutionEligibility, ExecutionEligibilityInput, ExecutionMandate, IndependentApproval, TrustedExecutionEvidence } from './policy.ts'

export type ReservationState = 'reserved' | 'blocked' | 'unknown'
export interface ExecutionReservation {
  state: ReservationState
  clientOrderId: string
  mandateId: string
  approvalId: string
  /** Immutable, unique fencing token; NEVER a venue order id or permission to skip execution risk. */
  reservationId?: string
  blockers: readonly string[]
  recordedAt: string
}

/** Untrusted selectors and intent. Never accept approval, mandate, risk evidence
 * or clock objects from callers. IDs only select server-owned records for reload.
 */
export interface ExecutionReservationRequest {
  mandateId: string
  approvalId: string
  accountId: string
  venue: string
  instrument: string
  side: 'buy' | 'sell'
  quantity: string
  reduceOnly: boolean
  requester: string
  clientOrderId: string
  intentHash: string
}

declare module '@deepseek-ai/cordis' {
  interface Context { pgTradingMandates: TradingMandatesService }
}

/** Contract only; importing this package installs NO persistent provider.
 * evaluate() is advisory only, never an order authorization.
 * reserve() MUST authenticate the requester, derive server clock and fresh risk
 * evidence itself, then load mandate + independently granted approval BY ID and
 * write reservation + one-time approval consumption in ONE durable transaction
 * keyed by clientOrderId and exact intent hash. Browser/model/strategy can pass
 * selectors but never approval status, permission revision, trusted risk evidence
 * or timestamp. Repeated same-hash requests return the existing reservation.
 * Different hashes MUST be rejected. Ambiguous commits return UNKNOWN and
 * recover by lookup, NEVER create a second reservation. Pause/revoke prevents
 * new reservations but not query/cancel/reconciliation for existing orders.
 * This service never sends orders; model self-approval is prohibited.
 */
export abstract class TradingMandatesService extends Service {
  constructor(ctx: Context) { super(ctx, 'pgTradingMandates') }
  abstract mandate(id: string): Promise<ExecutionMandate | undefined>
  abstract approval(id: string): Promise<IndependentApproval | undefined>
  /** Advisory only: input evidence may be caller supplied; result grants nothing. */
  abstract evaluate(input: ExecutionEligibilityInput): Promise<ExecutionEligibility>
  abstract reserve(input: ExecutionReservationRequest): Promise<ExecutionReservation>
  abstract reservationByClientOrderId(clientOrderId: string): Promise<ExecutionReservation | undefined>
  abstract pause(mandateId: string, actorId: string, reason: string): Promise<ExecutionMandate>
  abstract revoke(mandateId: string, actorId: string, reason: string): Promise<ExecutionMandate>
}

export default TradingMandatesService
