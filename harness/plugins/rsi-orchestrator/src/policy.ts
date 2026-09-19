/* Proposal policy only. No function in this module executes a plugin action. */
export type RsiActionClass = 'read' | 'compute' | 'external' | 'account' | 'trading'
export interface CapabilityDefinition { readonly id: string; readonly actionClass: RsiActionClass }

/** The original 22 PureGamma capability families, not a list of healthy installs. */
export const CAPABILITIES = [
  { id: 'auth', actionClass: 'account' },
  { id: 'agent-chat', actionClass: 'read' },
  { id: 'market-data', actionClass: 'read' },
  { id: 'data-sources', actionClass: 'compute' },
  { id: 'research', actionClass: 'read' },
  { id: 'research-runner', actionClass: 'compute' },
  { id: 'secretary', actionClass: 'external' },
  { id: 'skills', actionClass: 'compute' },
  { id: 'portfolio', actionClass: 'read' },
  { id: 'portfolio-autopilot', actionClass: 'trading' },
  { id: 'options', actionClass: 'read' },
  { id: 'backtest', actionClass: 'compute' },
  { id: 'memory', actionClass: 'account' },
  { id: 'trading', actionClass: 'trading' },
  { id: 'trading-mandates', actionClass: 'trading' },
  { id: 'nautilus-runtime', actionClass: 'trading' },
  { id: 'pg-tsy-runtime', actionClass: 'trading' },
  { id: 'notifications', actionClass: 'external' },
  { id: 'billing', actionClass: 'account' },
  { id: 'api-gateway', actionClass: 'account' },
  { id: 'mobile-api', actionClass: 'account' },
  { id: 'admin', actionClass: 'account' },
] as const satisfies readonly CapabilityDefinition[]

export type CapabilityId = typeof CAPABILITIES[number]['id']
export function isCapabilityId(value: unknown): value is CapabilityId {
  return typeof value === 'string' && CAPABILITIES.some((entry) => entry.id === value)
}

export interface RsiPreference {
  capabilityId: CapabilityId
  source: 'user-approved-memory'
  expiresAt: string
}

/** Interpret only vetted preference metadata, NEVER a free-text memory as a command. */
export function approvedPreferences(payload: unknown, now = Date.now()): RsiPreference[] {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return []
  const items = (payload as Record<string, unknown>).items
  if (!Array.isArray(items)) return []
  const preferences: RsiPreference[] = []
  for (const item of items) {
    if (typeof item !== 'object' || item === null || Array.isArray(item)) continue
    const data = item as Record<string, unknown>
    if (data.kind !== 'workflow_preference' || data.approved !== true || !isCapabilityId(data.capability_id)) continue
    if (typeof data.expires_at !== 'string') continue
    const expires = Date.parse(data.expires_at)
    if (!Number.isFinite(expires) || expires <= now) continue
    if (preferences.some((previous) => previous.capabilityId === data.capability_id)) continue
    preferences.push({ capabilityId: data.capability_id, source: 'user-approved-memory', expiresAt: data.expires_at })
  }
  return preferences.slice(0, 8)
}

export interface RsiDraftRequest {
  requestId: string
  task: string
  /** Caller-provided candidates are not installation or permission evidence. */
  candidateIds: readonly string[]
  /** Either explicitly provided by the current user or returned by a separately validated router. */
  selectedId?: string
  iteration?: number
}

export interface RsiDraft {
  requestId: string
  iteration: number
  mode: 'proposal_only'
  selected: CapabilityId | 'none'
  candidates: readonly CapabilityId[]
  memoryEligible: boolean
  memoryPreferenceUsed: boolean
  /** The planner has no execution adapter or authority, including for reads. */
  executionPermitted: false
  actionClass?: RsiActionClass
  requiresHumanApproval: boolean
  reason: string
}

const MAX_ITERATIONS = 3
const MAX_CANDIDATES = 8

export function draftRsiPlan(request: RsiDraftRequest, preferences: readonly RsiPreference[] = [], memoryEligible = false): RsiDraft {
  if (!/^[A-Za-z0-9._:-]{8,160}$/.test(request.requestId)) throw new Error('rsi request id invalid')
  if (typeof request.task !== 'string' || request.task.trim().length === 0 || request.task.length > 1024) throw new Error('rsi task invalid')
  const iteration = request.iteration ?? 0
  if (!Number.isInteger(iteration) || iteration < 0 || iteration >= MAX_ITERATIONS) throw new Error('rsi recursion limit exceeded')
  if (!Array.isArray(request.candidateIds) || request.candidateIds.length === 0 || request.candidateIds.length > MAX_CANDIDATES) throw new Error('rsi candidate limit exceeded')
  if (request.candidateIds.some((id) => !isCapabilityId(id))) throw new Error('rsi candidate is not in the installed-contract registry')
  const candidates = [...new Set(request.candidateIds)] as CapabilityId[]
  let selected: CapabilityId | 'none' = 'none'
  let memoryPreferenceUsed = false
  if (request.selectedId !== undefined) {
    if (request.selectedId !== 'none' && !candidates.includes(request.selectedId as CapabilityId)) throw new Error('rsi selection outside candidate set')
    selected = request.selectedId as CapabilityId | 'none'
  } else if (memoryEligible) {
    const match = preferences.find((entry) => candidates.includes(entry.capabilityId))
    if (match) { selected = match.capabilityId; memoryPreferenceUsed = true }
  }
  const definition = CAPABILITIES.find((entry) => entry.id === selected)
  return {
    requestId: request.requestId,
    iteration,
    mode: 'proposal_only',
    selected,
    candidates,
    memoryEligible,
    memoryPreferenceUsed,
    executionPermitted: false,
    actionClass: definition?.actionClass,
    requiresHumanApproval: definition !== undefined && definition.actionClass !== 'read',
    reason: selected === 'none' ? 'No validated selection; keep all tools idle.' :
      'Candidate proposal only: verify current Cordis installation, service health, identity, scope, consent, cost and approval at dispatch time.',
  }
}
