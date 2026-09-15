import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import ResearchSandboxService, {
  type ResearchArtifact,
  type ResearchRunDocument,
  type ResearchRunRequest,
  type ResearchSandboxJson,
} from '@puregamma/dsh-research-runner'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number; artifactTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(120000).default(30000),
  artifactTimeoutMs: z.number().min(100).max(120000).default(30000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): ResearchSandboxJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`research runner payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const output: Record<string, ResearchSandboxJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`research runner payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, ResearchSandboxJson> {
  if (!isRecord(value)) throw new Error('research runner compatibility API returned a non-object payload')
  return toJson(value) as Record<string, ResearchSandboxJson>
}
function identifier(value: string, label: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error(`${label} has an invalid format`)
  return normalized
}
function figureName(value: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 160 || normalized.includes('/') || normalized.includes('\\') || normalized === '.' || normalized === '..') throw new Error('research figure name is invalid')
  return normalized
}

export class LegacyApiResearchSandboxProvider extends ResearchSandboxService {
  static Config = Config
  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly artifactTimeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 30000
    this.artifactTimeoutMs = config.artifactTimeoutMs ?? 30000
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgResearchSandbox.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness research-runner compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private async fetchOwned(path: string, init: RequestInit, timeoutMs = this.timeoutMs): Promise<Response> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      return await fetch(new URL(`${this.baseUrl}${path}`), { ...init, signal: controller.signal })
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private async json(method: 'GET' | 'POST', path: string, body?: unknown): Promise<Record<string, ResearchSandboxJson>> {
    const response = await this.fetchOwned(path, {
      method,
      headers: { Accept: 'application/json', Authorization: `Bearer ${this.token()}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 500)
      throw new Error(`research runner compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
    }
    return toRecord(await response.json())
  }

  private document(payload: Record<string, ResearchSandboxJson>): ResearchRunDocument {
    return { kind: 'run', observedAt: new Date().toISOString(), source: 'compatibility:research-runner-api', payload }
  }

  async createRun(request: ResearchRunRequest): Promise<ResearchRunDocument> {
    const code = request.code
    if (!code.trim()) throw new Error('research code must not be empty')
    if (request.datasetRefs && request.datasetRefs.length > 8) throw new Error('research runner accepts at most 8 dataset refs')
    return this.document(await this.json('POST', '/research/run', {
      code,
      dataset_refs: request.datasetRefs ?? [],
      limits: request.limits ?? {},
      ...(request.idempotencyKey === undefined ? {} : { idempotency_key: request.idempotencyKey }),
    }))
  }
  async getRun(runId: string): Promise<ResearchRunDocument> {
    return this.document(await this.json('GET', `/research/run/${encodeURIComponent(identifier(runId, 'runId'))}`))
  }
  async cancelRun(runId: string): Promise<ResearchRunDocument> {
    return this.document(await this.json('POST', `/research/run/${encodeURIComponent(identifier(runId, 'runId'))}/cancel`))
  }
  async figure(runId: string, name: string): Promise<ResearchArtifact> {
    const safeRunId = identifier(runId, 'runId')
    const safeName = figureName(name)
    const response = await this.fetchOwned(`/research/run/${encodeURIComponent(safeRunId)}/files/${encodeURIComponent(safeName)}`, {
      method: 'GET', headers: { Accept: '*/*', Authorization: `Bearer ${this.token()}` },
    }, this.artifactTimeoutMs)
    if (!response.ok) throw new Error(`research figure API returned HTTP ${response.status}`)
    return {
      contentType: (response.headers.get('content-type') ?? 'application/octet-stream').split(';', 1)[0] ?? 'application/octet-stream',
      fileName: safeName,
      bytes: new Uint8Array(await response.arrayBuffer()),
    }
  }
}

export default LegacyApiResearchSandboxProvider
