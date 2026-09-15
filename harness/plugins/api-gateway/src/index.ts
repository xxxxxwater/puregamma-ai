import { Context, Service } from '@deepseek-ai/cordis'

export type GatewayJson = null | boolean | number | string | GatewayJson[] | { [key: string]: GatewayJson }
export type GatewayDocumentKind = 'catalog' | 'dashboard' | 'usage' | 'requests' | 'keys' | 'wallet' | 'key-mutation' | 'topup'

export interface GatewayDocument {
  kind: GatewayDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: GatewayJson }
}

export interface GatewayUsageQuery {
  start?: string
  end?: string
  granularity?: 'hour' | 'day'
  model?: string
  apiKeyId?: string
}

export interface GatewayRequestHistoryQuery { limit?: number; offset?: number }
export interface GatewayCreateKeyRequest { name?: string; rateLimitRpm?: number }
export interface GatewayTopupRequest { amountUsd: string; locale?: 'zh' | 'en' }
export type GatewayKeyStatus = 'active' | 'paused' | 'revoked'

declare module '@deepseek-ai/cordis' {
  interface Context { pgModelGateway: ModelGatewayService }
}

/**
 * PureGamma API Gateway product seam.
 *
 * This is deliberately NOT the OpenAI-compatible /v1 serving transport and is
 * not the Harness model loop. HTTP serving, admin policy and payment approval
 * remain separate plugins/consumers over this domain rather than a model tool.
 */
export abstract class ModelGatewayService extends Service {
  constructor(ctx: Context) { super(ctx, 'pgModelGateway') }

  abstract catalog(): Promise<GatewayDocument>
  abstract dashboard(): Promise<GatewayDocument>
  abstract usage(query?: GatewayUsageQuery): Promise<GatewayDocument>
  abstract requestHistory(query?: GatewayRequestHistoryQuery): Promise<GatewayDocument>
  abstract keys(): Promise<GatewayDocument>
  abstract wallet(): Promise<GatewayDocument>

  // Explicit UI/approval actions. Raw secrets may exist only in these return
  // values and must never be projected by the model-facing tool package.
  abstract createKey(request?: GatewayCreateKeyRequest): Promise<GatewayDocument>
  abstract setKeyStatus(keyId: string, status: GatewayKeyStatus): Promise<GatewayDocument>
  abstract rotateKey(keyId: string): Promise<GatewayDocument>
  abstract createTopup(request: GatewayTopupRequest): Promise<GatewayDocument>
}

export default ModelGatewayService
