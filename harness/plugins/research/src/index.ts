import { Context, Service } from '@deepseek-ai/cordis'

export type ResearchKind =
  | 'today'
  | 'overnight'
  | 'portfolio-impact'
  | 'upcoming-events'
  | 'opportunities'
  | 'alerts'

/** Harness-compatible lossless JSON tree. */
export type ResearchJson =
  | null
  | boolean
  | number
  | string
  | ResearchJson[]
  | { [key: string]: ResearchJson }

export interface ResearchDocument {
  kind: ResearchKind
  /** Compatibility payload's own data timestamp when present. */
  asOf?: string
  /** Time the provider observed/read this document. */
  observedAt: string
  /** Explicit health projection. Degraded results remain real results, never placeholders. */
  degraded: boolean
  source: string
  payload: { [key: string]: ResearchJson }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgResearch: ResearchService
  }
}

/**
 * Read-only evidence/research seam.
 *
 * This service owns normalized access to the stored research read models. It
 * deliberately does not own sandbox/deep-research execution; that belongs to a
 * separate research-runner plugin which may depend on this service.
 */
export abstract class ResearchService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgResearch')
  }

  abstract today(locale?: string): Promise<ResearchDocument>
  abstract overnight(sinceHours?: number): Promise<ResearchDocument>
  abstract portfolioImpact(): Promise<ResearchDocument>
  abstract upcomingEvents(days?: number): Promise<ResearchDocument>
  abstract opportunities(locale?: string): Promise<ResearchDocument>
  abstract alerts(): Promise<ResearchDocument>
}

export default ResearchService
