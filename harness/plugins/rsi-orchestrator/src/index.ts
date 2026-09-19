import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@puregamma/dsh-memory'
import { draftRsiPlan, type RsiDraft, type RsiDraftRequest } from './policy.ts'

export { CAPABILITIES, approvedPreferences, draftRsiPlan, isCapabilityId } from './policy.ts'
export type { CapabilityDefinition, CapabilityId, RsiActionClass, RsiDraft, RsiDraftRequest, RsiPreference } from './policy.ts'

export interface RsiProposalRequest extends RsiDraftRequest {
  /** Current-turn opt-in only. A memory setting is a second, independent gate. */
  useMemory?: boolean
}

declare module '@deepseek-ai/cordis' {
  interface Context { pgRsiPlanner: RsiPlanner }
}

/**
 * A Cordis service, NOT an agent with an execution tool. It neither dispatches
 * plugin methods nor sends conversation data to a model. The legacy memory API
 * exposes redacted previews only, not approved structured routing preferences;
 * consequently this implementation intentionally does not fetch or interpret
 * memory rows. A user-specific, approved metadata projection must land before
 * memory-informed selection can be enabled. Never change this to parse previews.
 */
export class RsiPlanner extends Service {
  constructor(ctx: Context) { super(ctx, 'pgRsiPlanner') }

  async propose(request: RsiProposalRequest): Promise<RsiDraft> {
    // Reject invalid requests before accessing a user-specific service.
    const basic = draftRsiPlan(request)
    if (request.useMemory !== true) return basic
    const memory = this.ctx.get('pgMemory')
    if (!memory) return basic
    try {
      const document = await memory.settings()
      const raw = document.payload.settings
      const settings = typeof raw === 'object' && raw !== null && !Array.isArray(raw)
        ? raw as Record<string, unknown> : undefined
      const eligible = settings?.consent_required === false && settings?.short_term_enabled === true && settings?.conversation_summary_enabled === true
      // Eligibility never equals retrieval or model-context injection.
      return draftRsiPlan(request, [], eligible)
    } catch {
      // Fail closed: zero memory reads, no raw error/credential exposure.
      return basic
    }
  }
}

export default RsiPlanner
