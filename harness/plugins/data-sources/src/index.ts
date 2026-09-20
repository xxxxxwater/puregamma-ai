import { Context, Service } from '@deepseek-ai/cordis'

export type DataSourceJson = null | boolean | number | string | DataSourceJson[] | { [key: string]: DataSourceJson }
export type DataSourceDocumentKind = 'catalog' | 'health' | 'preview' | 'runs' | 'fintwit-accounts' | 'mutation' | 'sync'

export interface DataSourceDocument {
  kind: DataSourceDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: DataSourceJson }
}

export interface FinTwitAccountUpdate {
  enabled?: boolean
  credibilityScore?: number
  accountWeight?: number
  providerUserId?: string
}

declare module '@deepseek-ai/cordis' {
  interface Context { pgDataSources: DataSourcesService }
}

/**
 * Data ingestion seam. Credentials are intentionally absent: secret material
 * belongs to Harness credentials/authorization, not data-source config payloads.
 */
export abstract class DataSourcesService extends Service {
  constructor(ctx: Context) { super(ctx, 'pgDataSources') }

  abstract catalog(): Promise<DataSourceDocument>
  abstract health(): Promise<DataSourceDocument>
  abstract preview(providerId: string): Promise<DataSourceDocument>
  abstract runs(providerId: string): Promise<DataSourceDocument>
  abstract fintwitAccounts(): Promise<DataSourceDocument>

  // Explicit operator/UI actions; never exposed as unrestricted model tools.
  abstract setEnabled(providerId: string, enabled: boolean): Promise<DataSourceDocument>
  abstract checkConfig(providerId: string): Promise<DataSourceDocument>
  abstract sync(providerId: string): Promise<DataSourceDocument>
  abstract syncAll(): Promise<DataSourceDocument>
  abstract updateFintwitAccount(accountId: string, update: FinTwitAccountUpdate): Promise<DataSourceDocument>
}

export default DataSourcesService
