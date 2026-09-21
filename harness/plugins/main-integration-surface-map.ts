import type { LegacySurfaceMigration } from './legacy-surface-map.js'
import type { LegacyWebSurfaceOwner } from './legacy-web-surface-map.js'

/**
 * Additive migration ledger for surfaces introduced on main after the original
 * refactor fork. The architecture gate reads this alongside the base ledgers.
 * Ownership is a migration obligation, NOT evidence that a Cordis client
 * plugin or production cutover has already implemented feature parity.
 */
export const MAIN_INTEGRATION_API_SURFACES: readonly LegacySurfaceMigration[] = [
  { surface: 'apps/api/routers/jev_advisory.py', target: 'research', disposition: 'provider', note: 'Read-only Jev judgement and provenance must become a research-owned Host Service/typed Remote; never grant model-driven trade execution.' },
]

export const MAIN_INTEGRATION_WEB_SURFACES: readonly LegacyWebSurfaceOwner[] = [
  { surface: 'apps/web/app/[locale]/jev-trader/page.tsx', owner: 'research', target: 'resource.research.jev-advisory', disposition: 'plugin-ui' },
]
