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
    pgResearchRuns: ResearchRunsService
  }
}

/**
 * Read-only evidence/research seam.
 *
 * This service owns normalized access to the stored research read models. It
 * deliberately does not own sandbox/deep-research execution; that belongs to a
 * separate research-runner plugin which may depend on this service.
 */
/**
 * Client presentation of one research read, persisted as the tool result's
 * `meta`. It carries provenance (as-of, observed, source, degraded) and the
 * payload's section names only, never the payload itself, so the view states
 * freshness without duplicating content the model already received.
 */
export interface ResearchDocumentPresentation {
  readonly schema: 'puregamma.research.document/v1'
  readonly kind: ResearchKind
  readonly asOf: string | null
  readonly observedAt: string
  readonly degraded: boolean
  readonly source: string
  readonly sections: readonly string[]
}

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

/** One deep-research run read (`run`, `runs`, `artifacts`, `evidence`), payload kept verbatim. */
export interface ResearchRunsDocument {
  kind: 'run' | 'runs' | 'artifacts' | 'evidence'
  observedAt: string
  source: string
  payload: { [key: string]: ResearchJson }
}

/**
 * One server-sent progress event of a deep-research run. `event` is the SSE
 * event name (`run.state`, `run.completed`, `run.failed`, `run.canceled`);
 * unknown names are passed through so consumers can ignore them.
 */
export interface ResearchRunEvent {
  event: string
  data: { [key: string]: ResearchJson }
}

export interface ResearchRunListRequest {
  limit?: number
  offset?: number
}

/**
 * Read-only seam over the user's deep-research runs (status, artifacts,
 * evidence and the progress stream). Creating, cancelling and retrying runs
 * are deliberately not part of this contract: they spend credits and stay
 * explicit actions of their owning surface.
 */
export abstract class ResearchRunsService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgResearchRuns')
  }

  abstract listRuns(request?: ResearchRunListRequest): Promise<ResearchRunsDocument>
  abstract run(runId: string): Promise<ResearchRunsDocument>
  abstract artifacts(runId: string): Promise<ResearchRunsDocument>
  abstract evidence(runId: string): Promise<ResearchRunsDocument>
  /** Progress events until the server ends the stream or `signal` aborts. */
  abstract events(runId: string, signal: AbortSignal): AsyncIterable<ResearchRunEvent>
}

export default ResearchService
