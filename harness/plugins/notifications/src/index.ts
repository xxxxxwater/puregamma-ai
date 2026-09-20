import { Context, Service } from '@deepseek-ai/cordis'

export type NotificationJson = null | boolean | number | string | NotificationJson[] | { [key: string]: NotificationJson }
export type NotificationChannel = 'telegram' | 'slack' | 'email' | 'imessage' | 'push'
export type NotificationDocumentKind = 'devices' | 'imessage-config' | 'verification' | 'daily-brief' | 'delivery' | 'deliveries' | 'mutation'

export interface NotificationDocument {
  kind: NotificationDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: NotificationJson }
}

export interface NotificationSendRequest {
  channel: NotificationChannel
  message: string
  idempotencyKey: string
  locale?: string
  metadata?: Record<string, NotificationJson>
}

export interface PushDeviceRequest {
  token: string
  environment?: string
  locale?: string
  timezone?: string
}

export interface DailyBriefUpdate {
  enabled?: boolean
  timezone?: string
  localTime?: string
  channel?: string
  channels?: string[]
  reportTypes?: string[]
  locale?: string
  includePortfolio?: boolean
  includeMarket?: boolean
  includeSignals?: boolean
  includeRisk?: boolean
  includeSentiment?: boolean
  quietHours?: Record<string, NotificationJson>
  maxLength?: number
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgNotifications: NotificationsService
  }
}

/** External-delivery seam. State-changing sends remain explicit service actions. */
export abstract class NotificationsService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgNotifications')
  }

  abstract devices(): Promise<NotificationDocument>
  abstract registerDevice(request: PushDeviceRequest): Promise<NotificationDocument>
  abstract unregisterDevice(request: PushDeviceRequest): Promise<NotificationDocument>
  abstract imessageConfig(): Promise<NotificationDocument>
  abstract requestImessageVerification(recipient: string): Promise<NotificationDocument>
  abstract confirmImessageVerification(challengeId: string, code: string): Promise<NotificationDocument>
  abstract testImessage(): Promise<NotificationDocument>
  abstract dailyBrief(): Promise<NotificationDocument>
  abstract updateDailyBrief(request: DailyBriefUpdate): Promise<NotificationDocument>
  abstract send(request: NotificationSendRequest): Promise<NotificationDocument>
  abstract deliveries(channel?: string): Promise<NotificationDocument>
}

export default NotificationsService
