import { Context, Service } from '@deepseek-ai/cordis'

export type MemoryJson =
  | null
  | boolean
  | number
  | string
  | MemoryJson[]
  | { [key: string]: MemoryJson }

export type MemoryScope = 'short_term' | 'mid_term' | 'all'
export type MemoryLocaleScope = 'chat' | 'secretary' | 'research' | 'portfolio'

export interface MemoryDocument {
  kind: 'settings' | 'items' | 'proposals' | 'proposal' | 'mutation' | 'export'
  observedAt: string
  source: string
  payload: { [key: string]: MemoryJson }
}

export interface MemorySettingsPatch {
  shortTermEnabled?: boolean
  midTermEnabled?: boolean
  conversationSummaryEnabled?: boolean
  researchMemoryEnabled?: boolean
  portfolioMemoryEnabled?: boolean
  /** Explicit user consent only. Callers must never synthesize this flag. */
  consentGranted?: boolean
}

export interface MemoryProposalQuery {
  status?: string
}

export interface MemoryExport {
  contentType: 'application/json'
  fileName?: string
  bytes: Uint8Array
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgMemory: MemoryService
  }
}

/**
 * User-owned memory management seam.
 *
 * This service is deliberately separate from model-context injection. Reading
 * settings/items for a UI does not grant a caller the right to inject those
 * rows into model context. Providers must preserve user scope opt-outs,
 * consent checks, secret redaction and write-disabled namespaces such as the
 * trading namespace.
 */
export abstract class MemoryService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgMemory')
  }

  abstract settings(): Promise<MemoryDocument>
  abstract updateSettings(patch: MemorySettingsPatch): Promise<MemoryDocument>
  abstract listItems(scope?: Exclude<MemoryScope, 'all'>): Promise<MemoryDocument>
  abstract listProposals(query?: MemoryProposalQuery): Promise<MemoryDocument>
  abstract approveProposal(proposalId: string): Promise<MemoryDocument>
  abstract rejectProposal(proposalId: string): Promise<MemoryDocument>
  abstract deleteItem(memoryId: string): Promise<MemoryDocument>
  abstract clear(scope?: MemoryScope): Promise<MemoryDocument>
  abstract exportDescriptor(): Promise<MemoryDocument>
  abstract exportData(): Promise<MemoryExport>
}

export default MemoryService
