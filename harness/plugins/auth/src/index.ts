import { Context, Service } from '@deepseek-ai/cordis'

export type AuthJson = null | boolean | number | string | AuthJson[] | { [key: string]: AuthJson }

export interface AuthUser {
  id: string
  email: string
  name: string
  role: string
  plan: string
  membershipTier?: string
  creditBalance: number
  avatarUrl?: string
  authProvider: string
  hasPassword: boolean
  emailVerified: boolean
  emailVerifiedAt?: string
  lastLoginAt?: string
  loginMethods: string[]
  locale: string
  createdAt: string
  updatedAt: string
}

export interface AuthOnboardingRequest {
  preferredAssets?: string[]
  preferredStyle?: string
  notificationChannels?: string[]
  telegramChatId?: string
  imessageRecipient?: string
}

export interface AuthMutation {
  ok: boolean
  observedAt: string
  source: string
  payload?: { [key: string]: AuthJson }
}

export interface AuthExport {
  contentType: 'application/json'
  fileName: string
  bytes: Uint8Array
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgAuth: AuthService
  }
}

/**
 * PureGamma account identity seam.
 *
 * Harness session persistence remains responsible for conversation sessions;
 * Harness credentials remain responsible for secret material. This service is
 * only the SaaS user/account domain and may be replaced independently.
 */
export abstract class AuthService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgAuth')
  }

  abstract currentUser(): Promise<AuthUser>
  abstract saveLocale(locale: string): Promise<AuthUser>
  abstract saveOnboarding(request: AuthOnboardingRequest): Promise<AuthMutation>
  abstract logout(): Promise<AuthMutation>
  abstract exportData(): Promise<AuthExport>
  abstract deleteAccount(emailConfirmation: string): Promise<AuthMutation>
}

export default AuthService
