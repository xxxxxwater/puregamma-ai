import { Context, Service } from '@deepseek-ai/cordis'

export type ResearchSandboxJson = null | boolean | number | string | ResearchSandboxJson[] | { [key: string]: ResearchSandboxJson }

export interface ResearchRunRequest {
  code: string
  datasetRefs?: string[]
  limits?: Record<string, ResearchSandboxJson>
  idempotencyKey?: string
}

export interface ResearchRunDocument {
  kind: 'run'
  observedAt: string
  source: string
  payload: { [key: string]: ResearchSandboxJson }
}

export interface ResearchArtifact {
  contentType: string
  fileName: string
  bytes: Uint8Array
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgResearchSandbox: ResearchSandboxService
  }
}

/**
 * Isolated research-code execution seam. User code must never execute in the
 * Harness host process. Providers are responsible for validation, entitlement,
 * queueing and a container/sandbox boundary before any code is evaluated.
 */
export abstract class ResearchSandboxService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgResearchSandbox')
  }

  abstract createRun(request: ResearchRunRequest): Promise<ResearchRunDocument>
  abstract getRun(runId: string): Promise<ResearchRunDocument>
  abstract cancelRun(runId: string): Promise<ResearchRunDocument>
  abstract figure(runId: string, name: string): Promise<ResearchArtifact>
}

export default ResearchSandboxService
