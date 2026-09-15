export type PureGammaCapabilityId =
  | 'auth'
  | 'market-data'
  | 'research'
  | 'portfolio'
  | 'options'
  | 'backtest'
  | 'memory'
  | 'trading'
  | 'notifications'
  | 'billing'
  | 'api-gateway'
  | 'admin'

export type CapabilityPlane = 'host' | 'client' | 'dual'
export type CapabilityRisk = 'read-only' | 'stateful' | 'money-movement'

/**
 * Stable metadata owned by a PureGamma Harness capability package.
 *
 * This replaces the old assumption that a Next route or FastAPI router is the
 * unit of product ownership. One capability may expose tools, remotes, jobs,
 * UI slots and one or more replaceable service providers.
 */
export interface PureGammaCapabilityDescriptor {
  id: PureGammaCapabilityId
  packageName: `@puregamma/dsh-${string}`
  plane: CapabilityPlane
  risk: CapabilityRisk
  /** Cordis/Harness service definitions consumed by other plugins. */
  services: readonly string[]
  /** Model-facing tools registered only when the capability is healthy. */
  tools: readonly string[]
  /** Browser slot/tool-view contributions. Empty means no direct UI. */
  ui: readonly string[]
  /** Existing code locations that are migration inputs, never dependencies. */
  legacyOwners: readonly string[]
}

/** Provider health is explicit so agents never infer availability from install state. */
export interface PureGammaProviderHealth {
  provider: string
  state: 'starting' | 'healthy' | 'degraded' | 'unavailable'
  observedAt: string
  detail?: string
}

/**
 * Money-moving plugins must expose a deterministic safety status independent
 * of the LLM. The model can request an action; it cannot bypass these gates.
 */
export interface PureGammaExecutionSafety {
  enabled: boolean
  killSwitchEngaged: boolean
  reconciliationHealthy: boolean
  ownershipVerified: boolean
  approvalRequired: boolean
  reason?: string
}
