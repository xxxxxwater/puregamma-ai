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
  /** Immutable, unique fencing token; NEVER a venue order id or a permission to skip execution risk. */
  reservationId?: string
  blockers: readonly string[]
  recordedAt: string
}

declare module '@deepseek-ai/cordis' {
  interface Context { pgTradingMandates: TradingMandatesService }
}

/** Contract only; NO provider is installed by importing this package.
 * Implementations must persist approval, mandate revisions, and reservations.
 * In particular reserve() is one atomic transaction keyed by clientOrderId:
 * check approved, active, unexpired, independently approved + exact intent hash,
 * write reservation, consume approval exactly once and return the same reservation
 * for the same clientOrderId/hash on retries. Different hashes MUST be rejected.
 * If commit outcome is ambiguous, return UNKNOWN and recover by lookup, never
 * mint a second token. Revoke/pause prevents new reservations but must not
 * conceal an already submitted order from query/cancel/reconciliation.
 * This service never sends orders and an LLM cannot approve its own request.
 */
export abstract class TradingMandatesService extends Service {
  constructor(ctx: Context) { super(ctx, 'pgTradingMandates') }
  abstract mandate(id: string): Promise<ExecutionMandate | undefined>
  abstract approval(id: string): Promise<IndependentApproval | undefined>
  abstract evaluate(input: ExecutionEligibilityInput): Promise<ExecutionEligibility>
  abstract reserve(input: ExecutionEligibilityInput): Promise<ExecutionReservation>
  abstract reservationByClientOrderId(clientOrderId: string): Promise<ExecutionReservation | undefined>
  abstract pause(mandateId: string, actorId: string, reason: string): Promise<ExecutionMandate>
  abstract revoke(mandateId: string, actorId: string, reason: string): Promise<ExecutionMandate>
}

export default TradingMandatesService
