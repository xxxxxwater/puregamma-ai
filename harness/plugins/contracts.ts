export type PureGammaCapabilityId =
  | 'auth'
  | 'agent-chat'
  | 'market-data'
  | 'data-sources'
  | 'research'
  | 'research-runner'
  | 'secretary'
  | 'skills'
  | 'portfolio'
  | 'portfolio-autopilot'
  | 'options'
  | 'backtest'
  | 'memory'
  | 'trading'
  | 'trading-mandates'
  | 'nautilus-runtime'
  | 'pg-tsy-runtime'
  | 'notifications'
  | 'billing'
  | 'api-gateway'
  | 'mobile-api'
  | 'admin'

export type CapabilityPlane = 'host' | 'client' | 'dual'
export type CapabilityRisk = 'read-only' | 'stateful' | 'money-movement'

/**
 * Stable metadata owned by one PureGamma Harness capability plugin.
 *
 * The application shell is deliberately absent from this union: it owns only
 * branding + conversation composition. Every former PureGamma.ai business
 * capability, integration and backend control surface must appear here or as a
 * provider plugin underneath one of these service definitions.
 */
export interface PureGammaCapabilityDescriptor {
  id: PureGammaCapabilityId
  packageName: `@puregamma/dsh-${string}`
  plane: CapabilityPlane
  risk: CapabilityRisk
  /** Cordis/Harness service definitions consumed by other plugins. */
  services: readonly string[]
  /** Model-facing tools registered only while required services are healthy. */
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
