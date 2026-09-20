import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import AuthService, {
  type AuthExport,
  type AuthJson,
  type AuthMutation,
  type AuthOnboardingRequest,
  type AuthUser,
} from '@puregamma/dsh-auth'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(10000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function str(value: unknown, fallback = ''): string { return typeof value === 'string' ? value : fallback }
function num(value: unknown, fallback = 0): number { return typeof value === 'number' && Number.isFinite(value) ? value : fallback }
function bool(value: unknown): boolean { return value === true }
function json(value: unknown, path = '$'): AuthJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`auth payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => json(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const out: Record<string, AuthJson> = {}
    for (const [key, item] of Object.entries(value)) out[key] = json(item, `${path}.${key}`)
    return out
  }
  throw new Error(`auth payload contains non-JSON value at ${path}`)
}

function normalizeUser(value: unknown): AuthUser {
  if (!isRecord(value)) throw new Error('auth compatibility API returned invalid user')
  return {
    id: str(value.id),
    email: str(value.email),
    name: str(value.name),
    role: str(value.role, 'user'),
    plan: str(value.plan, 'Free'),
    ...(typeof value.membership_tier === 'string' ? { membershipTier: value.membership_tier } : {}),
    creditBalance: num(value.credit_balance),
    ...(typeof value.avatar_url === 'string' && value.avatar_url ? { avatarUrl: value.avatar_url } : {}),
    authProvider: str(value.auth_provider, 'unknown'),
    hasPassword: bool(value.has_password),
    emailVerified: bool(value.email_verified),
    ...(typeof value.email_verified_at === 'string' ? { emailVerifiedAt: value.email_verified_at } : {}),
    ...(typeof value.last_login_at === 'string' ? { lastLoginAt: value.last_login_at } : {}),
    loginMethods: Array.isArray(value.login_methods) ? value.login_methods.filter((item): item is string => typeof item === 'string') : [],
    locale: str(value.locale, 'en'),
    createdAt: str(value.created_at),
    updatedAt: str(value.updated_at),
  }
}

export class LegacyApiAuthProvider extends AuthService {
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
    }, 'pgAuth.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness auth compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private async withResponse<T>(method: 'GET' | 'POST' | 'DELETE', path: string, body: unknown | undefined, consume: (response: Response) => Promise<T>): Promise<T> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(new URL(`${this.baseUrl}${path}`), {
        method,
        signal: controller.signal,
        headers: { Accept: 'application/json', Authorization: `Bearer ${this.token()}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      })
      return await consume(response)
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private async object(method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown): Promise<Record<string, unknown>> {
    return this.withResponse(method, path, body, async response => {
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 400)
        throw new Error(`auth compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      const payload = await response.json()
      if (!isRecord(payload)) throw new Error('auth compatibility API returned non-object JSON')
      return payload
    })
  }

  async currentUser(): Promise<AuthUser> {
    const payload = await this.object('GET', '/me')
    return normalizeUser(payload.user)
  }

  async saveLocale(locale: string): Promise<AuthUser> {
    const normalized = locale.trim().toLowerCase()
    if (!['en', 'zh'].includes(normalized)) throw new Error('locale must be en or zh')
    const payload = await this.object('POST', '/auth/preferences/locale', { locale: normalized })
    return normalizeUser(payload.user)
  }

  async saveOnboarding(request: AuthOnboardingRequest): Promise<AuthMutation> {
    const payload = await this.object('POST', '/auth/onboarding', {
      preferred_assets: request.preferredAssets ?? [],
      preferred_style: request.preferredStyle ?? 'risk-controlled',
      notification_channels: request.notificationChannels ?? ['email'],
      telegram_chat_id: request.telegramChatId ?? '',
      imessage_recipient: request.imessageRecipient ?? '',
    })
    return { ok: payload.ok === true, observedAt: new Date().toISOString(), source: 'compatibility:auth-api', payload: json(payload) as Record<string, AuthJson> }
  }

  async logout(): Promise<AuthMutation> {
    const payload = await this.object('POST', '/auth/logout')
    return { ok: payload.ok === true, observedAt: new Date().toISOString(), source: 'compatibility:auth-api' }
  }

  async exportData(): Promise<AuthExport> {
    return this.withResponse('GET', '/me/export', undefined, async response => {
      if (!response.ok) throw new Error(`auth account export returned HTTP ${response.status}`)
      const bytes = new TextEncoder().encode(JSON.stringify(await response.json(), null, 2))
      return { contentType: 'application/json', fileName: 'puregamma-account-export.json', bytes }
    })
  }

  async deleteAccount(emailConfirmation: string): Promise<AuthMutation> {
    const confirmation = emailConfirmation.trim()
    if (!confirmation || confirmation.length > 320) throw new Error('account deletion confirmation is invalid')
    const payload = await this.object('DELETE', '/me', { confirmation })
    return { ok: payload.ok === true, observedAt: new Date().toISOString(), source: 'compatibility:auth-api' }
  }
}

export default LegacyApiAuthProvider
