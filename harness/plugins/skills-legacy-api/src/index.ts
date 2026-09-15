import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import SkillsService, {
  type SkillDocument,
  type SkillImportRequest,
  type SkillInstallRequest,
  type SkillInvocationRequest,
  type SkillJson,
} from '@puregamma/dsh-skills'

export interface Config {
  baseUrl?: string
  authTokenEnv?: string
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(120000).default(30000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): SkillJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`skills compatibility payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const output: Record<string, SkillJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`skills compatibility payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, SkillJson> {
  if (!isRecord(value)) throw new Error('skills compatibility API returned a non-object payload')
  return toJson(value) as Record<string, SkillJson>
}
function id(value: string, label: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 128 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error(`${label} has an invalid format`)
  return normalized
}
function slug(value: string): string {
  const normalized = value.trim().toLowerCase()
  if (!normalized || normalized.length > 100 || !/^[a-z0-9][a-z0-9._-]*$/.test(normalized)) throw new Error('skill slug has an invalid format')
  return normalized
}

export class LegacyApiSkillsProvider extends SkillsService {
  static Config = Config
  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 30000
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgSkills.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness skills compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private async request(method: 'GET' | 'POST' | 'DELETE', path: string, options: { query?: Record<string, string | number | boolean | undefined>; body?: unknown } = {}): Promise<Record<string, SkillJson>> {
    const url = new URL(`${this.baseUrl}${path}`)
    for (const [key, value] of Object.entries(options.query ?? {})) if (value !== undefined) url.searchParams.set(key, String(value))
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(url, {
        method,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${this.token()}`,
          ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      })
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 400)
        throw new Error(`skills compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private document(kind: SkillDocument['kind'], payload: Record<string, SkillJson>): SkillDocument {
    return { kind, observedAt: new Date().toISOString(), source: 'compatibility:skills-api', payload }
  }

  async catalog(includeDisabled = false): Promise<SkillDocument> {
    return this.document('catalog', await this.request('GET', '/skills', { query: { include_disabled: includeDisabled } }))
  }
  async installations(): Promise<SkillDocument> { return this.document('installations', await this.request('GET', '/skills/installations')) }
  async runs(limit = 50): Promise<SkillDocument> {
    if (!Number.isInteger(limit) || limit < 1 || limit > 200) throw new Error('skill run limit must be 1-200')
    return this.document('runs', await this.request('GET', '/skills/runs', { query: { limit } }))
  }
  async run(skillSlug: string, inputs: Record<string, SkillJson> = {}, estimatedCredits = 0): Promise<SkillDocument> {
    if (!Number.isInteger(estimatedCredits) || estimatedCredits < 0 || estimatedCredits > 10000) throw new Error('estimatedCredits must be 0-10000')
    return this.document('run', await this.request('POST', `/skills/${encodeURIComponent(slug(skillSlug))}/run`, { body: { inputs, estimated_credits: estimatedCredits } }))
  }
  async runDetail(runId: string): Promise<SkillDocument> { return this.document('run', await this.request('GET', `/skills/runs/${encodeURIComponent(id(runId, 'runId'))}`)) }
  async importBundle(request: SkillImportRequest): Promise<SkillDocument> {
    return this.document('import', await this.request('POST', '/skills/import', { body: {
      source_type: request.sourceType,
      ...(request.repoUrl === undefined ? {} : { repo_url: request.repoUrl }),
      ...(request.commitHash === undefined ? {} : { commit_hash: request.commitHash }),
      files: request.files,
    } }))
  }
  async validateInvocation(request: SkillInvocationRequest): Promise<SkillDocument> {
    return this.document('validation', await this.request('POST', '/skills/validate-invocation', { body: {
      skill_refs: request.skillRefs,
      trigger_source: request.triggerSource,
      allow_autopilot: request.allowAutopilot ?? false,
      allow_order_intent: request.allowOrderIntent ?? false,
      estimated_credits: request.estimatedCredits ?? 0,
    } }))
  }
  async detail(skillId: string): Promise<SkillDocument> { return this.document('skill', await this.request('GET', `/skills/${encodeURIComponent(id(skillId, 'skillId'))}`)) }
  async install(skillId: string, request: SkillInstallRequest = {}): Promise<SkillDocument> {
    return this.document('installation', await this.request('POST', `/skills/${encodeURIComponent(id(skillId, 'skillId'))}/install`, { body: {
      ...(request.pinnedVersion === undefined ? {} : { pinned_version: request.pinnedVersion }),
      ...(request.workspaceId === undefined ? {} : { workspace_id: request.workspaceId }),
      config_overrides: request.configOverrides ?? {},
    } }))
  }
  async uninstall(installationId: string): Promise<SkillDocument> {
    return this.document('mutation', await this.request('DELETE', `/skills/installations/${encodeURIComponent(id(installationId, 'installationId'))}`))
  }
}

export default LegacyApiSkillsProvider
