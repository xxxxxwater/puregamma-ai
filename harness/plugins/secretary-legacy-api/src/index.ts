import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import SecretaryService, {
  type SecretaryAudio,
  type SecretaryLocale,
  type SecretaryMessage,
  type SecretaryMutation,
  type SecretaryReply,
  type SecretaryReplyRequest,
  type SecretarySkillState,
  type SecretaryState,
  type SecretaryTranscription,
  type SecretaryVoiceRequest,
} from '@puregamma/dsh-secretary'

export interface Config {
  baseUrl?: string
  authTokenEnv?: string
  requestTimeoutMs?: number
  voiceTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(10000),
  voiceTimeoutMs: z.number().min(1000).max(180000).default(120000),
})

const AUDIO_TYPES = new Set(['audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav', 'audio/x-wav', 'audio/mpeg'])

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function stringValue(value: unknown, fallback = ''): string { return typeof value === 'string' ? value : fallback }
function finiteNumber(value: unknown, fallback = 0): number { return typeof value === 'number' && Number.isFinite(value) ? value : fallback }
function boolValue(value: unknown, fallback = false): boolean { return typeof value === 'boolean' ? value : fallback }

function message(value: unknown): SecretaryMessage {
  if (!isRecord(value)) throw new Error('secretary compatibility API returned an invalid message')
  return { id: stringValue(value.id), role: stringValue(value.role), content: stringValue(value.content), createdAt: stringValue(value.created_at) }
}

function skill(value: unknown): SecretarySkillState | undefined {
  if (!isRecord(value) || typeof value.id !== 'string') return undefined
  return { id: value.id, status: stringValue(value.status, 'unknown'), risk: stringValue(value.risk, 'unknown') }
}

function normalizeLocale(value: SecretaryLocale | undefined): SecretaryLocale { return value === 'en' ? 'en' : 'zh' }
function normalizeIdempotencyKey(value: string): string {
  const normalized = value.trim()
  if (normalized.length < 16 || normalized.length > 80 || !/^[A-Za-z0-9_-]+$/.test(normalized)) {
    throw new Error('secretary idempotency key must be 16-80 URL-safe characters')
  }
  return normalized
}

export class LegacyApiSecretaryProvider extends SecretaryService {
  static Config = Config

  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly voiceTimeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 10000
    this.voiceTimeoutMs = config.voiceTimeoutMs ?? 120000
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgSecretary.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness secretary compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private url(path: string): URL { return new URL(`${this.baseUrl}${path}`) }

  private async withResponse<T>(path: string, init: RequestInit, consume: (response: Response) => Promise<T>, timeoutMs = this.timeoutMs): Promise<T> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetch(this.url(path), { ...init, signal: controller.signal })
      return await consume(response)
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private async json(method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown): Promise<Record<string, unknown>> {
    return this.withResponse(path, {
      method,
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${this.token()}`,
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }, async response => {
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 400)
        throw new Error(`secretary compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      const payload = await response.json()
      if (!isRecord(payload)) throw new Error('secretary compatibility API returned a non-object payload')
      return payload
    })
  }

  async state(locale: SecretaryLocale = 'zh'): Promise<SecretaryState> {
    const payload = await this.json('GET', `/secretary?locale=${encodeURIComponent(normalizeLocale(locale))}`)
    const voice = isRecord(payload.voice) ? payload.voice : {}
    const memory = isRecord(payload.memory) ? payload.memory : {}
    const billing = isRecord(payload.billing) ? payload.billing : {}
    const skills = Array.isArray(payload.skills) ? payload.skills.map(skill).filter((item): item is SecretarySkillState => item !== undefined) : []
    return {
      observedAt: new Date().toISOString(),
      source: 'compatibility:secretary-api',
      ...(typeof payload.conversation_id === 'string' && payload.conversation_id ? { conversationId: payload.conversation_id } : {}),
      messages: Array.isArray(payload.messages) ? payload.messages.map(message) : [],
      voice: { id: stringValue(voice.id, 'unknown'), name: stringValue(voice.name, 'unknown'), fixed: boolValue(voice.fixed) },
      skills,
      memory: { enabled: boolValue(memory.enabled), isolatedByUser: boolValue(memory.isolated_by_user) },
      billing: { creditsPerReply: finiteNumber(billing.credits_per_reply), creditBalance: finiteNumber(billing.credit_balance) },
    }
  }

  async reply(request: SecretaryReplyRequest): Promise<SecretaryReply> {
    const content = request.content.trim()
    if (!content || content.length > 4000) throw new Error('secretary reply content must be 1-4000 characters')
    const payload = await this.json('POST', '/secretary/messages', {
      content,
      locale: normalizeLocale(request.locale),
      request_id: normalizeIdempotencyKey(request.idempotencyKey),
    })
    return {
      userMessage: message(payload.user_message),
      assistantMessage: message(payload.assistant_message),
      creditsUsed: finiteNumber(payload.credits_used),
      creditBalance: finiteNumber(payload.credit_balance),
    }
  }

  async synthesizeVoice(request: SecretaryVoiceRequest): Promise<SecretaryAudio> {
    const text = request.text.trim()
    if (!text || text.length > 1500) throw new Error('secretary voice text must be 1-1500 characters')
    return this.withResponse('/secretary/voice', {
      method: 'POST',
      headers: { Accept: 'audio/*', Authorization: `Bearer ${this.token()}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, locale: normalizeLocale(request.locale) }),
    }, async response => {
      const contentType = (response.headers.get('content-type') ?? '').split(';', 1)[0]?.trim() || 'application/octet-stream'
      if (!response.ok || !contentType.startsWith('audio/')) throw new Error(`secretary voice API returned HTTP ${response.status} (${contentType})`)
      const voiceId = response.headers.get('x-pg-voice-id') ?? undefined
      return {
        contentType,
        ...(voiceId ? { voiceId } : {}),
        bytes: new Uint8Array(await response.arrayBuffer()),
      }
    }, this.voiceTimeoutMs)
  }

  async transcribe(audio: Uint8Array, contentType: string, locale: SecretaryLocale = 'zh'): Promise<SecretaryTranscription> {
    const normalizedType = contentType.split(';', 1)[0]?.trim().toLowerCase() ?? ''
    if (!AUDIO_TYPES.has(normalizedType)) throw new Error(`unsupported secretary audio type: ${normalizedType || 'empty'}`)
    if (audio.byteLength < 512 || audio.byteLength > 2_000_000) throw new Error('secretary audio must be between 512 and 2000000 bytes')
    const body = new Blob([Uint8Array.from(audio)], { type: normalizedType })
    return this.withResponse(`/secretary/transcribe?locale=${encodeURIComponent(normalizeLocale(locale))}`, {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: `Bearer ${this.token()}`, 'Content-Type': normalizedType },
      body,
    }, async response => {
      if (!response.ok) throw new Error(`secretary transcription API returned HTTP ${response.status}`)
      const payload = await response.json()
      if (!isRecord(payload) || typeof payload.text !== 'string') throw new Error('secretary transcription API returned invalid payload')
      return { text: payload.text, language: payload.language === 'en' ? 'en' : 'zh' }
    }, this.voiceTimeoutMs)
  }

  async clearConversation(): Promise<SecretaryMutation> {
    const payload = await this.json('DELETE', '/secretary/memory')
    return { ok: payload.ok === true, observedAt: new Date().toISOString(), source: 'compatibility:secretary-api' }
  }
}

export default LegacyApiSecretaryProvider
