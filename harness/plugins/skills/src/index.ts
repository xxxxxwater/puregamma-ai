import { Context, Service } from '@deepseek-ai/cordis'

export type SkillJson = null | boolean | number | string | SkillJson[] | { [key: string]: SkillJson }
export type SkillDocumentKind = 'catalog' | 'installations' | 'runs' | 'run' | 'skill' | 'validation' | 'import' | 'installation' | 'mutation'

export interface SkillDocument {
  kind: SkillDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: SkillJson }
}

export interface SkillImportRequest {
  sourceType: 'upload' | 'github'
  repoUrl?: string
  commitHash?: string
  files: Record<string, string>
}

export interface SkillInstallRequest {
  pinnedVersion?: string
  workspaceId?: string
  configOverrides?: Record<string, SkillJson>
}

export interface SkillInvocationRequest {
  skillRefs: Array<Record<string, SkillJson>>
  triggerSource: 'agent_chat' | 'dashboard' | 'report' | 'portfolio' | 'autopilot' | 'nautilus' | 'api' | 'scheduled_job'
  allowAutopilot?: boolean
  allowOrderIntent?: boolean
  estimatedCredits?: number
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgSkills: SkillsService
  }
}

/**
 * Stable skill registry/workflow seam.
 *
 * Installation, source validation, manifest policy, tool allowlists, cost
 * limits, autopilot permission and order-intent permission belong behind this
 * service. Consumers must never import the legacy Python registry directly.
 */
export abstract class SkillsService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgSkills')
  }

  abstract catalog(includeDisabled?: boolean): Promise<SkillDocument>
  abstract installations(): Promise<SkillDocument>
  abstract runs(limit?: number): Promise<SkillDocument>
  abstract run(slug: string, inputs?: Record<string, SkillJson>, estimatedCredits?: number): Promise<SkillDocument>
  abstract runDetail(runId: string): Promise<SkillDocument>
  abstract importBundle(request: SkillImportRequest): Promise<SkillDocument>
  abstract validateInvocation(request: SkillInvocationRequest): Promise<SkillDocument>
  abstract detail(skillId: string): Promise<SkillDocument>
  abstract install(skillId: string, request?: SkillInstallRequest): Promise<SkillDocument>
  abstract uninstall(installationId: string): Promise<SkillDocument>
}

export default SkillsService
