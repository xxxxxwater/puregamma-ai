import { Context, Service } from '@deepseek-ai/cordis'

export type AdminJson = null | boolean | number | string | AdminJson[] | { [key: string]: AdminJson }
export type AdminDocumentKind =
  | 'overview'
  | 'system-status'
  | 'llm-status'
  | 'llm-cost-summary'
  | 'agent-runs'
  | 'agent-run'
  | 'reports'
  | 'deliveries'
  | 'alerts'
  | 'skill-runs'
  | 'portfolio-sync'
  | 'backtests'
  | 'trading'
  | 'stripe-summary'

export interface AdminDocument {
  kind: AdminDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: AdminJson }
}

export interface AdminListQuery {
  limit?: number
  offset?: number
  status?: string
  userId?: string
}

declare module '@deepseek-ai/cordis' {
  interface Context { pgAdmin: AdminService }
}

/**
 * Read-only PureGamma business observability seam.
 *
 * Domain mutations remain with Billing/DataSources/Gateway/Trading services.
 * Plugin inventory is intentionally absent: DeepSeek Harness already projects
 * ctx.loader directly through its native host plugin-inventory service.
 */
export abstract class AdminService extends Service {
  constructor(ctx: Context) { super(ctx, 'pgAdmin') }

  abstract overview(): Promise<AdminDocument>
  abstract systemStatus(): Promise<AdminDocument>
  abstract llmStatus(): Promise<AdminDocument>
  abstract llmCostSummary(): Promise<AdminDocument>
  abstract agentRuns(): Promise<AdminDocument>
  abstract agentRun(runId: string): Promise<AdminDocument>
  abstract reports(query?: AdminListQuery): Promise<AdminDocument>
  abstract deliveries(query?: AdminListQuery): Promise<AdminDocument>
  abstract alerts(query?: AdminListQuery): Promise<AdminDocument>
  abstract skillRuns(query?: AdminListQuery): Promise<AdminDocument>
  abstract portfolioSync(query?: AdminListQuery): Promise<AdminDocument>
  abstract backtests(query?: AdminListQuery): Promise<AdminDocument>
  abstract trading(query?: AdminListQuery): Promise<AdminDocument>
  abstract stripeSummary(): Promise<AdminDocument>
}

export default AdminService
