import { Context, Service } from '@deepseek-ai/cordis'

export type SecretaryLocale = 'zh' | 'en'
export type SecretaryJson = null | boolean | number | string | SecretaryJson[] | { [key: string]: SecretaryJson }

export interface SecretaryMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool' | string
  content: string
  createdAt: string
}

export interface SecretarySkillState {
  id: string
  status: string
  risk: string
}

export interface SecretaryState {
  observedAt: string
  source: string
  conversationId?: string
  messages: SecretaryMessage[]
  voice: {
    id: string
    name: string
    fixed: boolean
  }
  skills: SecretarySkillState[]
  memory: {
    enabled: boolean
    isolatedByUser: boolean
  }
  billing: {
    creditsPerReply: number
    creditBalance: number
  }
}

export interface SecretaryReplyRequest {
  content: string
  locale: SecretaryLocale
  /** Stable caller-owned key. Retries of the same logical reply must reuse it. */
  idempotencyKey: string
}

export interface SecretaryReply {
  userMessage: SecretaryMessage
  assistantMessage: SecretaryMessage
  creditsUsed: number
  creditBalance: number
}

export interface SecretaryVoiceRequest {
  text: string
  locale: SecretaryLocale
}

export interface SecretaryAudio {
  contentType: string
  voiceId?: string
  bytes: Uint8Array
}

export interface SecretaryTranscription {
  text: string
  language: SecretaryLocale
}

export interface SecretaryMutation {
  ok: boolean
  observedAt: string
  source: string
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgSecretary: SecretaryService
  }
}

/**
 * Private-secretary capability seam.
 *
 * This is deliberately not a second Agent runtime. Harness owns the permanent
 * conversation loop. During migration the service can still reach the legacy
 * secretary transport for parity (history, reply, TTS, STT and clear), while
 * client/conversation plugins consume this seam. Native Harness providers can
 * replace the compatibility provider without changing the shell.
 */
export abstract class SecretaryService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgSecretary')
  }

  abstract state(locale?: SecretaryLocale): Promise<SecretaryState>
  abstract reply(request: SecretaryReplyRequest): Promise<SecretaryReply>
  abstract synthesizeVoice(request: SecretaryVoiceRequest): Promise<SecretaryAudio>
  abstract transcribe(audio: Uint8Array, contentType: string, locale?: SecretaryLocale): Promise<SecretaryTranscription>
  abstract clearConversation(): Promise<SecretaryMutation>
}

export default SecretaryService
