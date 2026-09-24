import { createHash } from 'node:crypto'
import { Service } from '@deepseek-ai/cordis'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@puregamma/dsh-auth'
import {
  ChatWorkspaceError,
  DEFAULT_ATTACHMENT_LIMITS,
  STALE_UPLOAD_HOURS,
  assertOwned,
  checkContextChars,
  checkFileBytes,
  checkFileCount,
  checkUserByteBudget,
  permissionMode,
  staleUploadDecision,
  toolPermission as decideToolPermission,
  type AttachmentLimits,
  type PermissionMode,
  type ToolPermission,
} from './policy.ts'

export * from './policy.ts'

/** Bytes of inline text one historical attachment reference may carry. */
const MAX_INLINE_REFERENCE_BYTES = 20_000

/** Attachment content path, unchanged from the classic so existing clients keep working. */
const ATTACHMENT_CONTENT_PATH = '/api/agent/attachments'

export type AttachmentKind = 'image' | 'file'

/** One attachment as the tenant-owned storage reports it. */
export interface AttachmentRecord {
  id: string
  /** The owner this row belongs to. Re-checked by this seam on every read. */
  userId: string
  name: string
  mime: string
  kind: AttachmentKind
  /** Stored bytes; 0 once the payload was freed. */
  size: number
  sha256: string
  /** Context text extracted at upload time; empty once freed. */
  extractedText: string
  /** True when payload and extracted text were freed by their owner. */
  removed: boolean
}

/** A row about to be written. The seam computes `sha256` and bounds every field. */
export interface NewAttachment {
  userId: string
  name: string
  mime: string
  kind: AttachmentKind
  payload: Uint8Array
  extractedText: string
  sha256: string
}

/** A row that still holds bytes and is old enough to count as abandoned. */
export interface StaleCandidate {
  id: string
  createdAtMs: number
}

/**
 * The tenant-owned attachment storage this seam is a provider boundary over.
 *
 * The contract every implementation must hold:
 *
 * - **Every query takes the authenticated user id and filters by it in the
 *   query.** Ownership enforced only by the caller is not ownership: a port that
 *   can return another tenant's row is unusable here, whatever the caller does
 *   with it afterwards.
 * - **Nothing degrades.** A failed or ambiguous query throws, and an empty
 *   result means "no such row for this user" — never "unknown, carry on".
 * - **A freed row keeps its identity.** `freeBytes` drops payload and extracted
 *   text and zeroes `size`, so a historical message can still say what was sent
 *   while no bytes remain to serve.
 * - **Quota checks are serialized per user.** A `usedBytes` read and the matching
 *   `insertAttachment` must not interleave with another upload by the same user;
 *   this seam cannot create that lock itself.
 */
export interface ChatWorkspaceStore {
  /** The stored mode of a conversation this user owns. `found: false` means no such conversation for this user. */
  permissionMode(userId: string, conversationId: string): Promise<{ found: boolean; mode: string | null }>
  /** Bytes this user currently holds across every stored attachment. */
  usedBytes(userId: string): Promise<number>
  insertAttachment(row: NewAttachment): Promise<AttachmentRecord>
  attachment(userId: string, attachmentId: string): Promise<AttachmentRecord | undefined>
  /** Frees payload and extracted text of the given rows and reports how many held bytes. */
  freeBytes(userId: string, attachmentIds: readonly string[]): Promise<number>
  /** Ids carried by this user's stored messages, optionally limited to one conversation. */
  referencedAttachmentIds(userId: string, conversationId?: string): Promise<readonly string[]>
  /** Rows of this user that still hold bytes and were created before the cutoff. */
  staleCandidates(userId: string, beforeMs: number): Promise<readonly StaleCandidate[]>
}

/** A new upload handed to the seam. Payload bytes are stored, never decoded here. */
export interface AttachmentInput {
  name: string
  payload: Uint8Array
  mime: string
  kind: AttachmentKind
  /** Context text extracted by the upload boundary; this seam enforces its size, it does not extract it. */
  extractedText?: string
}

/** What a caller is told about a stored attachment. Never the payload itself. */
export interface AttachmentMetadata {
  id: string
  name: string
  mime: string
  size: number
  sha256: string
  kind: AttachmentKind
  /** True once the owner freed it: the record survives, the bytes and the URL do not. */
  removed: boolean
  /** Empty when removed — a link to a freed file would be a 404 dressed up as a download. */
  url: string
}

/** One entry a stored turn carries: a stored attachment id, or inline text. */
export interface ResolvedAttachment {
  /** Present for stored attachments; inline text from a historical message has no row. */
  id?: string
  name: string
  mime: string
  content: string
  size?: number
  sha256?: string
  kind?: AttachmentKind
  removed?: boolean
  url?: string
}

export interface Config {
  /** Bytes of one stored attachment. Overrides AGENT_ATTACHMENT_MAX_BYTES. */
  maxFileBytes?: number
  /** Bytes one user may hold. Overrides AGENT_ATTACHMENT_USER_BYTES. */
  maxUserBytes?: number
  /** Attachments per turn. Overrides AGENT_ATTACHMENT_MAX_FILES. */
  maxFiles?: number
  /** Characters of extracted context per turn. Overrides AGENT_ATTACHMENT_MAX_CONTEXT_CHARS. */
  maxContextChars?: number
}

export const Config: z<Config> = z.object({
  maxFileBytes: z.number().min(1).default(DEFAULT_ATTACHMENT_LIMITS.maxFileBytes),
  maxUserBytes: z.number().min(1).default(DEFAULT_ATTACHMENT_LIMITS.maxUserBytes),
  maxFiles: z.number().min(1).default(DEFAULT_ATTACHMENT_LIMITS.maxFiles),
  maxContextChars: z.number().min(1).default(DEFAULT_ATTACHMENT_LIMITS.maxContextChars),
})

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgChatWorkspace: ChatWorkspaceService
  }
}

/**
 * PureGamma tenant-owned attachments and per-conversation execution permissions.
 *
 * The permission decision is the security-critical half: it is computed
 * server-side from the conversation's stored mode and never from a field a
 * client supplied, and a tool nobody has classified is refused in the two
 * restrictive modes. The attachment half owns durable, tenant-owned storage with
 * a per-user byte allowance that is reclaimable, because a quota nothing can
 * release is a dead end for the user.
 *
 * No method accepts an identity, a permission mode or an "already authorized"
 * flag from a caller: the requester is always the authenticated session.
 */
export abstract class ChatWorkspaceService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgChatWorkspace')
  }

  /** The mode a conversation runs under. An unknown or unowned conversation is refused. */
  abstract permissionMode(conversationId: string): Promise<PermissionMode>
  /** Whether one tool may run in a conversation: 'allow', 'ask' or 'deny'. */
  abstract toolPermission(conversationId: string, tool: string): Promise<ToolPermission>
  abstract saveAttachment(input: AttachmentInput): Promise<AttachmentMetadata>
  /** The stored row, or a refusal. A row owned by somebody else is never returned. */
  abstract ownedAttachment(attachmentId: string): Promise<AttachmentRecord>
  /** Free the bytes of one attachment, keeping the record of what it was. */
  abstract removeAttachment(attachmentId: string): Promise<AttachmentMetadata>
  /** Free the bytes a deleted conversation had sent, and report how many rows were freed. */
  abstract releaseConversationAttachments(conversationId: string): Promise<number>
  /** Resolve the attachment references a turn carries into model context. */
  abstract resolveAttachments(items: readonly unknown[]): Promise<readonly ResolvedAttachment[]>
}

/**
 * Provider over the tenant-owned attachment storage.
 *
 * This is a migration/provider boundary, not a second implementation of the
 * rules: the rules live in the pure policy, and every query below is issued with
 * the authenticated user id and filtered by it in storage. When ownership cannot
 * be established — no authentication capability, no session, no storage, an
 * unknown conversation, a stored mode nobody recognises — the seam refuses with
 * a typed error instead of degrading to a default, a zero or an empty list.
 */
export class TenantChatWorkspaceProvider extends ChatWorkspaceService {
  static Config = Config

  private readonly limits: AttachmentLimits
  private readonly attachments: ChatWorkspaceStore | undefined

  constructor(ctx: Context, config: Config = {}, attachments?: ChatWorkspaceStore) {
    super(ctx)
    const env = attachmentLimits(process.env)
    this.limits = {
      maxFileBytes: config.maxFileBytes ?? env.maxFileBytes,
      maxUserBytes: config.maxUserBytes ?? env.maxUserBytes,
      maxFiles: config.maxFiles ?? env.maxFiles,
      maxContextChars: config.maxContextChars ?? env.maxContextChars,
    }
    this.attachments = attachments
  }

  async permissionMode(conversationId: string): Promise<PermissionMode> {
    const userId = await this.owner()
    const store = this.storage()
    if (typeof conversationId !== 'string' || conversationId.length === 0) {
      throw new ChatWorkspaceError('CONVERSATION_NOT_FOUND')
    }
    const stored = await store.permissionMode(userId, conversationId)
    // A conversation this user does not own is not distinguishable from one that
    // does not exist, and neither may inherit a mode by default: refuse both.
    if (!stored.found) throw new ChatWorkspaceError('CONVERSATION_NOT_FOUND')
    // A NULL column is the classic "never chose one" and takes the default; any
    // other unrecognised value is refused rather than coerced.
    return permissionMode(stored.mode)
  }

  async toolPermission(conversationId: string, tool: string): Promise<ToolPermission> {
    return decideToolPermission(await this.permissionMode(conversationId), tool)
  }

  async saveAttachment(input: AttachmentInput): Promise<AttachmentMetadata> {
    const userId = await this.owner()
    const store = this.storage()
    if (!isRecord(input)) throw new ChatWorkspaceError('ATTACHMENT_INVALID')
    const name = attachmentName(input.name)
    if (!(input.payload instanceof Uint8Array)) throw new ChatWorkspaceError('ATTACHMENT_INVALID')
    const mime = attachmentMime(input.mime)
    if (input.kind !== 'image' && input.kind !== 'file') throw new ChatWorkspaceError('ATTACHMENT_INVALID')
    const extractedText = typeof input.extractedText === 'string' ? input.extractedText : ''

    const size = checkFileBytes({ bytes: input.payload.byteLength, limits: this.limits })
    if (!size.allowed) throw new ChatWorkspaceError(size.reason)
    const context = checkContextChars({ chars: extractedText.length, limits: this.limits })
    if (!context.allowed) throw new ChatWorkspaceError(context.reason)

    // The quota is checked against what is stored, and an allowance spent on
    // uploads the user abandoned and can no longer see is reclaimed before the
    // upload is refused: refusing outright would be a dead end with nothing for
    // the user to act on.
    let used = await store.usedBytes(userId)
    let admitted = checkUserByteBudget({ usedBytes: used, incomingBytes: input.payload.byteLength, limits: this.limits })
    if (!admitted.allowed) {
      await this.releaseStaleUploads(store, userId)
      used = await store.usedBytes(userId)
      admitted = checkUserByteBudget({ usedBytes: used, incomingBytes: input.payload.byteLength, limits: this.limits })
    }
    if (!admitted.allowed) throw new ChatWorkspaceError(admitted.reason)

    const row = await store.insertAttachment({
      userId,
      name,
      mime,
      kind: input.kind,
      payload: input.payload,
      extractedText,
      sha256: createHash('sha256').update(input.payload).digest('hex'),
    })
    return this.metadata(row)
  }

  async ownedAttachment(attachmentId: string): Promise<AttachmentRecord> {
    const userId = await this.owner()
    const store = this.storage()
    if (typeof attachmentId !== 'string' || attachmentId.length === 0) {
      throw new ChatWorkspaceError('ATTACHMENT_NOT_FOUND')
    }
    const row = await store.attachment(userId, attachmentId)
    if (row === undefined) throw new ChatWorkspaceError('ATTACHMENT_NOT_FOUND')
    // Defence in depth: the query above is already user-scoped, and a row that
    // still belongs to somebody else is a storage contract violation, so it is
    // refused rather than served.
    if (!assertOwned(userId, row.userId).allowed) throw new ChatWorkspaceError('ATTACHMENT_NOT_FOUND')
    return row
  }

  async removeAttachment(attachmentId: string): Promise<AttachmentMetadata> {
    const userId = await this.owner()
    const store = this.storage()
    const row = await this.ownedAttachment(attachmentId)
    const freed = await store.freeBytes(userId, [row.id])
    if (freed === 0) throw new ChatWorkspaceError('ATTACHMENT_NOT_FOUND')
    // The record survives with its identity; only the bytes are gone.
    return this.metadata({ ...row, size: 0, extractedText: '', removed: true })
  }

  async releaseConversationAttachments(conversationId: string): Promise<number> {
    const userId = await this.owner()
    const store = this.storage()
    if (typeof conversationId !== 'string' || conversationId.length === 0) {
      throw new ChatWorkspaceError('CONVERSATION_NOT_FOUND')
    }
    const ids = await store.referencedAttachmentIds(userId, conversationId)
    if (ids.length === 0) return 0
    return store.freeBytes(userId, ids)
  }

  async resolveAttachments(items: readonly unknown[]): Promise<readonly ResolvedAttachment[]> {
    const userId = await this.owner()
    const store = this.storage()
    if (!Array.isArray(items)) throw new ChatWorkspaceError('ATTACHMENT_INVALID')
    const count = checkFileCount({ count: items.length, limits: this.limits })
    if (!count.allowed) throw new ChatWorkspaceError(count.reason)

    // A stored turn is JSON from the database, not a typed payload: every entry
    // is re-validated here rather than trusted.
    const list: readonly unknown[] = items
    const resolved: ResolvedAttachment[] = []
    for (const item of list) {
      if (!isRecord(item)) throw new ChatWorkspaceError('ATTACHMENT_INVALID')
      if (typeof item.id === 'string' && item.id.length > 0) {
        const row = await store.attachment(userId, item.id)
        // The draft it belonged to was deleted before this turn was sent: a
        // tidied-up draft must not fail the send.
        if (row === undefined) continue
        if (!assertOwned(userId, row.userId).allowed) throw new ChatWorkspaceError('ATTACHMENT_NOT_FOUND')
        const metadata = this.metadata(row)
        // A deliberately freed file is not evidence the model should see, and
        // re-uploading it is not our decision to make.
        if (metadata.removed) continue
        resolved.push({ ...metadata, content: row.extractedText })
        continue
      }
      // Existing clients and historical inline text remain supported.
      const content = typeof item.content === 'string' ? item.content : ''
      if (new TextEncoder().encode(content).length > MAX_INLINE_REFERENCE_BYTES) {
        throw new ChatWorkspaceError('ATTACHMENT_TEXT_LIMIT')
      }
      resolved.push({ name: sanitizeName(item.name) || 'attachment', mime: 'text/plain', content })
    }
    const chars = resolved.reduce((total, item) => total + item.content.length, 0)
    const context = checkContextChars({ chars, limits: this.limits })
    if (!context.allowed) throw new ChatWorkspaceError(context.reason)
    return resolved
  }

  /** The authenticated identity, or a refusal. Never a caller-supplied id. */
  private async owner(): Promise<string> {
    const auth = this.ctx.get('pgAuth')
    if (auth === undefined) throw new ChatWorkspaceError('WORKSPACE_NOT_AUTHORIZED')
    let id: string
    try {
      id = (await auth.currentUser()).id
    } catch {
      throw new ChatWorkspaceError('WORKSPACE_NOT_AUTHORIZED')
    }
    if (typeof id !== 'string' || id.length === 0) throw new ChatWorkspaceError('WORKSPACE_NOT_AUTHORIZED')
    return id
  }

  /** An unconfigured storage refuses: it never degrades into a working-looking empty state. */
  private storage(): ChatWorkspaceStore {
    if (this.attachments === undefined) throw new ChatWorkspaceError('WORKSPACE_STORE_UNAVAILABLE')
    return this.attachments
  }

  private metadata(row: AttachmentRecord): AttachmentMetadata {
    const removed = row.removed || row.size === 0
    return {
      id: row.id,
      name: row.name,
      mime: row.mime,
      size: row.size,
      sha256: row.sha256,
      kind: row.kind,
      removed,
      url: removed ? '' : ATTACHMENT_CONTENT_PATH + '/' + row.id + '/content',
    }
  }

  /**
   * Reclaim uploads that were never sent anywhere and are no longer being
   * composed. The pure predicate decides, this method only applies it.
   */
  private async releaseStaleUploads(store: ChatWorkspaceStore, userId: string): Promise<number> {
    const nowMs = Date.now()
    const cutoffMs = nowMs - STALE_UPLOAD_HOURS * 3_600_000
    const candidates = await store.staleCandidates(userId, cutoffMs)
    if (candidates.length === 0) return 0
    const referenced = new Set(await store.referencedAttachmentIds(userId))
    const releasable = candidates
      .filter((candidate) => staleUploadDecision({
        createdAtMs: candidate.createdAtMs,
        nowMs,
        referenced: referenced.has(candidate.id),
      }).allowed)
      .map((candidate) => candidate.id)
    if (releasable.length === 0) return 0
    return store.freeBytes(userId, releasable)
  }
}

export default TenantChatWorkspaceProvider

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The classic keeps the last path component, drops control characters and bounds the name. */
function sanitizeName(value: unknown): string {
  if (typeof value !== 'string') return ''
  const base = value.replace(/\\/g, '/').split('/').pop() ?? ''
  return [...base].filter((char) => char.charCodeAt(0) >= 32).join('').slice(0, 160)
}

/** A name a caller wants stored: sanitized, and refused when nothing usable is left. */
function attachmentName(value: unknown): string {
  const name = sanitizeName(value)
  if (name.length === 0) throw new ChatWorkspaceError('ATTACHMENT_INVALID')
  return name
}

function attachmentMime(value: unknown): string {
  if (typeof value !== 'string') throw new ChatWorkspaceError('ATTACHMENT_INVALID')
  const mime = value.trim()
  if (mime.length === 0 || mime.length > 160) throw new ChatWorkspaceError('ATTACHMENT_INVALID')
  return mime
}

/**
 * Attachment limits from the environment.
 *
 * The two byte limits keep the classic variable names; the classic's fixed caps
 * are configurable too. A present-but-unusable override is refused loudly rather
 * than falling back to a limit the operator did not choose — and never to an
 * unbounded one, since a malformed limit would otherwise disable the quota.
 */
export function attachmentLimits(env: Record<string, string | undefined> = process.env): AttachmentLimits {
  return {
    maxFileBytes: parseLimit(env.AGENT_ATTACHMENT_MAX_BYTES, DEFAULT_ATTACHMENT_LIMITS.maxFileBytes),
    maxUserBytes: parseLimit(env.AGENT_ATTACHMENT_USER_BYTES, DEFAULT_ATTACHMENT_LIMITS.maxUserBytes),
    maxFiles: parseLimit(env.AGENT_ATTACHMENT_MAX_FILES, DEFAULT_ATTACHMENT_LIMITS.maxFiles),
    maxContextChars: parseLimit(env.AGENT_ATTACHMENT_MAX_CONTEXT_CHARS, DEFAULT_ATTACHMENT_LIMITS.maxContextChars),
  }
}

function parseLimit(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw.trim() === '') return fallback
  const value = Number(raw)
  if (!Number.isSafeInteger(value) || value < 1) throw new ChatWorkspaceError('INVALID_ATTACHMENT_LIMIT')
  return value
}
