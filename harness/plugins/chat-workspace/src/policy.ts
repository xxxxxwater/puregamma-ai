/**
 * Pure, fail-closed policy for tenant-owned durable attachments and
 * per-conversation execution permissions.
 *
 * Architecture (deliberately one-directional):
 *
 *     upload / tool call  ---->  pgChatWorkspace  ---->  tenant-owned storage
 *                                   (this policy is       (rows keyed by the
 *                                    the only thing         authenticated user id)
 *                                    that decides)
 *
 * Two invariants live here, and neither is negotiable:
 *
 * 1. **The permission decision is server-side and fail-closed.** It is computed
 *    from the conversation's stored mode, never from a client-supplied field. A
 *    tool nobody has classified is refused in the two restrictive modes instead
 *    of being promoted to a confirmation the user did not expect, and a mode
 *    that is not in `PERMISSION_MODES` is refused instead of defaulted.
 * 2. **Ownership is authorization.** Every attachment decision is taken against
 *    the authenticated user id, and an unverifiable owner is refused rather than
 *    assumed equal.
 *
 * This module is intentionally free of Cordis, of node:fs, of the network and of
 * every import, so the invariants above can be unit-tested directly. Attachment
 * limits arrive as arguments: reading the environment is the provider's job.
 */

// ------------------------------------------------------------------ permissions

export const PERMISSION_MODES = ['read-only', 'workspace-write', 'full-access'] as const

export type PermissionMode = (typeof PERMISSION_MODES)[number]

/** The mode a conversation gets when it has never chosen one. */
export const DEFAULT_PERMISSION_MODE: PermissionMode = 'workspace-write'

export const INVALID_PERMISSION_MODE = 'INVALID_PERMISSION_MODE'

/**
 * Resolve a stored permission mode, or refuse.
 *
 * An unset mode (`null` / `undefined` / the empty string) takes the classic
 * default; anything else that is not one of the three modes raises
 * `INVALID_PERMISSION_MODE` rather than being coerced to a default. A typo in a
 * deployment or in a stored column must never silently become a mode the user
 * did not choose.
 */
export function permissionMode(value: string | null | undefined): PermissionMode {
  const mode = value ? value : DEFAULT_PERMISSION_MODE
  if (!(PERMISSION_MODES as readonly string[]).includes(mode)) throw new ChatWorkspaceError(INVALID_PERMISSION_MODE)
  return mode as PermissionMode
}

/**
 * Read-only tools: allowed in every permission mode.
 *
 * `generate_order_preview` and `run_nautilus_backtest` are named explicitly
 * because they are read-only by construction, and the confirmation card stays
 * reserved for calls that really do change or spend something: an order PREVIEW
 * changes no state, and the research plan's market-data backtest runs on stored
 * data. Prompting for these only teaches the user to click through the card
 * without reading it.
 */
export const READ_TOOLS: ReadonlySet<string> = new Set([
  'get_market_quote', 'get_market_history', 'get_recent_news', 'search_news',
  'search_source_documents', 'search_online_sources', 'get_defi_protocol_metrics',
  'get_chain_metrics', 'get_onchain_snapshot', 'get_data_source_status',
  'list_research_strategies', 'get_strategy_performance', 'get_sentiment_context',
  'get_account_snapshot', 'get_position_snapshot', 'get_open_orders',
  'get_strategy_status', 'get_options_context', 'get_earnings_gamma',
  'generate_order_preview', 'run_nautilus_backtest',
])

/**
 * Requires confirmation in "workspace-write". Empty today because no tool in the
 * agent's registry mutates account, plan, balance or filesystem state; the set is
 * the explicit home for the first one that does, so it cannot ship as an
 * unreviewed implicit "ask" by falling outside READ_TOOLS.
 */
export const STATEFUL_TOOLS: ReadonlySet<string> = new Set<string>()

export type ToolPermission = 'allow' | 'ask' | 'deny'

/**
 * Additional restriction only; existing entitlement/control-plane gates still apply.
 *
 * Read-only tools are allowed in every mode; tools that change state require an
 * explicit confirmation in "workspace-write" and are refused in "read-only"; a
 * tool nobody has classified is refused in the two restrictive modes rather
 * than silently promoted to a confirmation the user did not expect.
 */
export function toolPermission(mode: string, tool: string): ToolPermission {
  const resolved = permissionMode(mode)
  if (READ_TOOLS.has(tool)) return 'allow'
  if (resolved === 'full-access') return 'allow'
  if (resolved === 'read-only') return 'deny'
  return STATEFUL_TOOLS.has(tool) ? 'ask' : 'deny'
}

// --------------------------------------------------------------------- refusals

export type WorkspaceReason =
  | 'INVALID_PERMISSION_MODE'
  | 'INVALID_ATTACHMENT_LIMIT'
  | 'CONVERSATION_NOT_FOUND'
  | 'WORKSPACE_NOT_AUTHORIZED'
  | 'WORKSPACE_STORE_UNAVAILABLE'
  | 'ATTACHMENT_NOT_FOUND'
  | 'ATTACHMENT_INVALID'
  | 'ATTACHMENT_SIZE_LIMIT'
  | 'ATTACHMENT_STORAGE_LIMIT'
  | 'ATTACHMENT_COUNT_LIMIT'
  | 'ATTACHMENT_TEXT_LIMIT'
  // Refusals to *release* bytes: the upload is referenced, or still inside the
  // window in which it may yet be sent. They are decisions, never thrown.
  | 'ATTACHMENT_REFERENCED'
  | 'ATTACHMENT_RECENT'

/**
 * The seam's single refusal shape: a typed code.
 *
 * Mirrors the classic's `ValueError("CODE")` / `LookupError("ATTACHMENT_NOT_FOUND")`,
 * so a caller can tell a refusal apart from a bug instead of pattern-matching on
 * a message. It is thrown at the boundary; the pure helpers below return a
 * decision carrying the same code.
 */
export class ChatWorkspaceError extends Error {
  readonly code: WorkspaceReason

  constructor(code: WorkspaceReason) {
    super(code)
    this.name = 'ChatWorkspaceError'
    this.code = code
  }
}

export interface PolicyAllowed {
  readonly allowed: true
}

export interface PolicyRefused {
  readonly allowed: false
  readonly reason: WorkspaceReason
}

/** An explicit decision. There is no third state, and no silent truncation. */
export type PolicyDecision = PolicyAllowed | PolicyRefused

function allow(): PolicyAllowed {
  return { allowed: true }
}

function refuse(reason: WorkspaceReason): PolicyRefused {
  return { allowed: false, reason }
}

// ----------------------------------------------------------------------- limits

export interface AttachmentLimits {
  /** Bytes of one stored attachment. */
  maxFileBytes: number
  /** Bytes one user may hold across every stored attachment. */
  maxUserBytes: number
  /** Attachments one turn may carry. */
  maxFiles: number
  /** Characters of extracted context one turn may carry. */
  maxContextChars: number
}

export const MAX_FILE_BYTES = 10_485_760
export const MAX_USER_BYTES = 104_857_600
export const MAX_FILES = 8
export const MAX_CONTEXT_CHARS = 50_000

/** The classic defaults. The provider may override them from its configuration. */
export const DEFAULT_ATTACHMENT_LIMITS: AttachmentLimits = {
  maxFileBytes: MAX_FILE_BYTES,
  maxUserBytes: MAX_USER_BYTES,
  maxFiles: MAX_FILES,
  maxContextChars: MAX_CONTEXT_CHARS,
}

/**
 * A limit that cannot be evaluated refuses.
 *
 * `NaN` is the trap this exists for: every comparison against it is false, so an
 * unset or malformed limit would silently become an unbounded allowance instead
 * of a refusal. The same guard covers negative and non-finite values.
 */
function usable(limit: number): boolean {
  return Number.isFinite(limit) && limit >= 0
}

/** One attachment: non-empty, and never larger than the file limit. */
export function checkFileBytes(input: { bytes: number; limits: AttachmentLimits }): PolicyDecision {
  if (!usable(input.limits.maxFileBytes) || !Number.isFinite(input.bytes)) return refuse('ATTACHMENT_SIZE_LIMIT')
  if (input.bytes < 1 || input.bytes > input.limits.maxFileBytes) return refuse('ATTACHMENT_SIZE_LIMIT')
  return allow()
}

/** The per-user byte budget. Exactly at the budget is allowed; one byte over is not. */
export function checkUserByteBudget(input: { usedBytes: number; incomingBytes: number; limits: AttachmentLimits }): PolicyDecision {
  const { usedBytes, incomingBytes, limits } = input
  if (!usable(limits.maxUserBytes) || !Number.isFinite(usedBytes) || !Number.isFinite(incomingBytes)) {
    return refuse('ATTACHMENT_STORAGE_LIMIT')
  }
  if (usedBytes < 0 || incomingBytes < 0) return refuse('ATTACHMENT_STORAGE_LIMIT')
  return usedBytes + incomingBytes > limits.maxUserBytes ? refuse('ATTACHMENT_STORAGE_LIMIT') : allow()
}

/** Attachments per turn. */
export function checkFileCount(input: { count: number; limits: AttachmentLimits }): PolicyDecision {
  if (!usable(input.limits.maxFiles) || !Number.isFinite(input.count)) return refuse('ATTACHMENT_COUNT_LIMIT')
  if (input.count < 0 || input.count > input.limits.maxFiles) return refuse('ATTACHMENT_COUNT_LIMIT')
  return allow()
}

/** Characters of extracted context one turn carries into the model. */
export function checkContextChars(input: { chars: number; limits: AttachmentLimits }): PolicyDecision {
  if (!usable(input.limits.maxContextChars) || !Number.isFinite(input.chars)) return refuse('ATTACHMENT_TEXT_LIMIT')
  if (input.chars < 0 || input.chars > input.limits.maxContextChars) return refuse('ATTACHMENT_TEXT_LIMIT')
  return allow()
}

// ------------------------------------------------------------------- retention

/** How long an unsent upload is kept before it may be reclaimed. */
export const STALE_UPLOAD_HOURS = 24

/**
 * May an abandoned upload's bytes be reclaimed?
 *
 * An upload the user abandoned still counts against the allowance while being
 * invisible: it is not in the composer (that state is gone) and not in any
 * message. Reclaiming those is what makes a full allowance recoverable without
 * the user having to find something to delete.
 *
 * The window is the classic's `created_at < utcnow() - older_than_hours`: strictly
 * older, so an upload sitting exactly on the 24h boundary is still treated as
 * being composed and is kept.
 *
 * Releasing frees bytes the user cannot see, so every unverifiable input — an
 * unusable window, a non-finite timestamp — refuses to release rather than
 * guessing. The failure direction is deliberate: keeping a stale upload costs
 * allowance, freeing a live one loses content.
 */
export function staleUploadDecision(input: {
  createdAtMs: number
  nowMs: number
  referenced: boolean
  olderThanHours?: number
}): PolicyDecision {
  const hours = input.olderThanHours ?? STALE_UPLOAD_HOURS
  if (!Number.isFinite(hours) || hours < 0) return refuse('ATTACHMENT_RECENT')
  if (!Number.isFinite(input.createdAtMs) || !Number.isFinite(input.nowMs)) return refuse('ATTACHMENT_RECENT')
  // A referenced upload is evidence a message was sent with; it is never reclaimed.
  if (input.referenced) return refuse('ATTACHMENT_REFERENCED')
  const cutoffMs = input.nowMs - hours * 3_600_000
  return input.createdAtMs < cutoffMs ? allow() : refuse('ATTACHMENT_RECENT')
}

// ------------------------------------------------------------------- ownership

/**
 * Ownership is a security property, not a convenience check.
 *
 * A row belongs to exactly one tenant, and a request may only ever address a row
 * whose owner is the authenticated user. An unverifiable pair — either side
 * missing — is refused too: "unknown owner" is not "the same owner". Ids are
 * opaque and are compared verbatim; normalizing them here would let a padded id
 * match one it is not.
 *
 * The refusal is `ATTACHMENT_NOT_FOUND` on purpose: a cross-tenant probe must not
 * be able to tell "someone else's row" from "no such row".
 *
 * This predicate is defence in depth ONLY. It is not authorization: the storage
 * query must ALSO filter by the authenticated user id, because a pure helper
 * that runs after the bytes were already read has authorized nothing.
 */
export function assertOwned(userId: string | null | undefined, rowUserId: string | null | undefined): PolicyDecision {
  const owner = typeof userId === 'string' ? userId : ''
  const row = typeof rowUserId === 'string' ? rowUserId : ''
  if (owner.length === 0 || row.length === 0) return refuse('ATTACHMENT_NOT_FOUND')
  return owner === row ? allow() : refuse('ATTACHMENT_NOT_FOUND')
}
