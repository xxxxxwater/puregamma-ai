import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import MemoryService, {
  type MemoryDocument,
  type MemoryExport,
  type MemoryJson,
  type MemoryProposalQuery,
  type MemoryScope,
  type MemorySettingsPatch,
} from '@puregamma/dsh-memory'

export interface Config {
  baseUrl?: string
  authTokenEnv?: string
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(10000),
})

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toMemoryJson(value: unknown, path = '$'): MemoryJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`memory compatibility payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toMemoryJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const output: Record<string, MemoryJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toMemoryJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`memory compatibility payload contains non-JSON value at ${path}`)
}

function toMemoryRecord(value: unknown): Record<string, MemoryJson> {
  if (!isRecord(value)) throw new Error('memory compatibility API returned a non-object payload')
  return toMemoryJson(value) as Record<string, MemoryJson>
}

function normalizeIdentifier(value: string, label: string): string {
  const normalized = value.trim()
  if (normalized.length < 1 || normalized.length > 128 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) {
    throw new Error(`${label} has an invalid format`)
  }
  return normalized
}

function normalizeStatus(value: string | undefined): string | undefined {
  if (value === undefined) return undefined
  const normalized = value.trim()
  if (normalized.length === 0) return undefined
  if (normalized.length > 64 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error('proposal status has an invalid format')
  return normalized
}

function normalizeScope(value: MemoryScope): MemoryScope {
  if (value !== 'short_term' && value !== 'mid_term' && value !== 'all') throw new Error('invalid memory scope')
  return value
}

function fileNameFromDisposition(header: string | null): string | undefined {
  if (!header) return undefined
  const match = header.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i)
  return match?.[1]?.trim()
}

/**
 * Migration provider for user-owned memory management.
 *
 * It preserves the existing server's ownership, consent, namespace policy,
 * secret-redaction and audit enforcement. Finite HTTP requests are also held
 * by a Cordis-owned AbortController set so plugin unload cannot strand them.
 */
export class LegacyApiMemoryProvider extends MemoryService {
  static Config = Config

  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 10000

    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgMemory.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness memory compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private controller(): AbortController {
    const controller = new AbortController()
    this.controllers.add(controller)
    return controller
  }

  private release(controller: AbortController): void {
    this.controllers.delete(controller)
  }

  private url(path: string, query: Record<string, string | number | undefined> = {}): URL {
    const url = new URL(`${this.baseUrl}${path}`)
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
    return url
  }

  private async requestJson(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    options: { query?: Record<string, string | number | undefined>; body?: unknown } = {},
  ): Promise<Record<string, MemoryJson>> {
    const controller = this.controller()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(this.url(path, options.query), {
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
        throw new Error(`memory compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toMemoryRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.release(controller)
    }
  }

  private document(kind: MemoryDocument['kind'], payload: Record<string, MemoryJson>): MemoryDocument {
    return {
      kind,
      observedAt: new Date().toISOString(),
      source: 'compatibility:memory-api',
      payload,
    }
  }

  async settings(): Promise<MemoryDocument> {
    return this.document('settings', await this.requestJson('GET', '/memory/settings'))
  }

  async updateSettings(patch: MemorySettingsPatch): Promise<MemoryDocument> {
    const body: Record<string, boolean> = {}
    if (patch.shortTermEnabled !== undefined) body.short_term_enabled = patch.shortTermEnabled
    if (patch.midTermEnabled !== undefined) body.mid_term_enabled = patch.midTermEnabled
    if (patch.conversationSummaryEnabled !== undefined) body.conversation_summary_enabled = patch.conversationSummaryEnabled
    if (patch.researchMemoryEnabled !== undefined) body.research_memory_enabled = patch.researchMemoryEnabled
    if (patch.portfolioMemoryEnabled !== undefined) body.portfolio_memory_enabled = patch.portfolioMemoryEnabled
    if (patch.consentGranted !== undefined) body.consent_granted = patch.consentGranted
    if (Object.keys(body).length === 0) throw new Error('memory settings patch must contain at least one field')
    return this.document('settings', await this.requestJson('PATCH', '/memory/settings', { body }))
  }

  async listItems(scope: 'short_term' | 'mid_term' = 'short_term'): Promise<MemoryDocument> {
    const normalized = normalizeScope(scope)
    if (normalized === 'all') throw new Error('memory item listing does not accept all scope')
    return this.document('items', await this.requestJson('GET', '/memory/items', { query: { scope: normalized } }))
  }

  async listProposals(query: MemoryProposalQuery = {}): Promise<MemoryDocument> {
    return this.document('proposals', await this.requestJson('GET', '/memory/proposals', {
      query: { status: normalizeStatus(query.status) },
    }))
  }

  async approveProposal(proposalId: string): Promise<MemoryDocument> {
    const id = normalizeIdentifier(proposalId, 'proposalId')
    return this.document('proposal', await this.requestJson('POST', `/memory/proposals/${encodeURIComponent(id)}/approve`))
  }

  async rejectProposal(proposalId: string): Promise<MemoryDocument> {
    const id = normalizeIdentifier(proposalId, 'proposalId')
    return this.document('proposal', await this.requestJson('POST', `/memory/proposals/${encodeURIComponent(id)}/reject`))
  }

  async deleteItem(memoryId: string): Promise<MemoryDocument> {
    const id = normalizeIdentifier(memoryId, 'memoryId')
    return this.document('mutation', await this.requestJson('DELETE', `/memory/items/${encodeURIComponent(id)}`))
  }

  async clear(scope: MemoryScope = 'all'): Promise<MemoryDocument> {
    const normalized = normalizeScope(scope)
    return this.document('mutation', await this.requestJson('POST', '/memory/clear', {
      body: { scope: normalized },
    }))
  }

  async exportDescriptor(): Promise<MemoryDocument> {
    return this.document('export', await this.requestJson('GET', '/memory/export'))
  }

  async exportData(): Promise<MemoryExport> {
    const controller = this.controller()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(this.url('/memory/export', { download: 1 }), {
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${this.token()}`,
        },
      })
      if (!response.ok) throw new Error(`memory export API returned HTTP ${response.status}`)
      const fileName = fileNameFromDisposition(response.headers.get('content-disposition'))
      return {
        contentType: 'application/json',
        ...(fileName === undefined ? {} : { fileName }),
        bytes: new Uint8Array(await response.arrayBuffer()),
      }
    } finally {
      clearTimeout(timer)
      this.release(controller)
    }
  }
}

export default LegacyApiMemoryProvider
