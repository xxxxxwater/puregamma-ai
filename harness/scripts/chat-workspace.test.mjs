import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ChatWorkspaceError,
  DEFAULT_ATTACHMENT_LIMITS,
  MAX_CONTEXT_CHARS,
  MAX_FILES,
  MAX_FILE_BYTES,
  MAX_USER_BYTES,
  PERMISSION_MODES,
  READ_TOOLS,
  STALE_UPLOAD_HOURS,
  STATEFUL_TOOLS,
  assertOwned,
  checkContextChars,
  checkFileBytes,
  checkFileCount,
  checkUserByteBudget,
  permissionMode,
  staleUploadDecision,
  toolPermission,
} from '../plugins/chat-workspace/src/policy.ts'
import { TenantChatWorkspaceProvider, attachmentLimits } from '../plugins/chat-workspace/src/index.ts'

const HOUR_MS = 3_600_000
const LIMITS = DEFAULT_ATTACHMENT_LIMITS

/** The exact roster the classic classified; adding or dropping an entry is a behaviour change. */
const CLASSIC_READ_TOOLS = [
  'get_market_quote', 'get_market_history', 'get_recent_news', 'search_news',
  'search_source_documents', 'search_online_sources', 'get_defi_protocol_metrics',
  'get_chain_metrics', 'get_onchain_snapshot', 'get_data_source_status',
  'list_research_strategies', 'get_strategy_performance', 'get_sentiment_context',
  'get_account_snapshot', 'get_position_snapshot', 'get_open_orders',
  'get_strategy_status', 'get_options_context', 'get_earnings_gamma',
  'generate_order_preview', 'run_nautilus_backtest',
].sort()

const refusal = (code) => (error) => error instanceof ChatWorkspaceError && error.code === code

// ------------------------------------------------------------------ permissions

test('the read-only roster is the classic roster, entry for entry', () => {
  assert.deepEqual([...READ_TOOLS].sort(), CLASSIC_READ_TOOLS)
  // The two entries the classic names explicitly are the ones most likely to be
  // "cleaned up" by mistake; they are read-only by construction.
  assert.equal(READ_TOOLS.has('generate_order_preview'), true)
  assert.equal(READ_TOOLS.has('run_nautilus_backtest'), true)
  assert.deepEqual(PERMISSION_MODES, ['read-only', 'workspace-write', 'full-access'])
})

test('every read-only tool is allowed in every mode', () => {
  for (const mode of PERMISSION_MODES) {
    for (const tool of READ_TOOLS) {
      assert.equal(toolPermission(mode, tool), 'allow', mode + ' / ' + tool)
    }
  }
})

test('a tool nobody classified is denied in both restrictive modes and allowed only in full-access', () => {
  // The fail-closed core: an unclassified tool is never promoted to a
  // confirmation the user did not expect, and never silently allowed.
  for (const tool of ['place_order', 'transfer_funds', 'delete_account', '', 'get_market_quote ']) {
    assert.equal(toolPermission('read-only', tool), 'deny', tool)
    assert.equal(toolPermission('workspace-write', tool), 'deny', tool)
    assert.equal(toolPermission('full-access', tool), 'allow', tool)
  }
})

test('the confirmation set is empty, so no tool can become an unexpected "ask"', () => {
  assert.equal(STATEFUL_TOOLS.size, 0)
  // Nothing can reach the "ask" branch by falling outside READ_TOOLS; the branch
  // exists so the first genuinely stateful tool ships as a reviewed entry.
  const unreachable = [...READ_TOOLS].every((tool) => toolPermission('workspace-write', tool) === 'allow')
  assert.equal(unreachable, true)
})

test('an unknown permission mode is rejected instead of defaulted', () => {
  for (const value of ['admin', 'workspace_write', 'FULL-ACCESS', ' read-only', '  ', 'true']) {
    assert.throws(() => permissionMode(value), refusal('INVALID_PERMISSION_MODE'), JSON.stringify(value))
    assert.throws(() => toolPermission(value, 'get_market_quote'), refusal('INVALID_PERMISSION_MODE'), value)
  }
  // Only a genuinely unset mode takes the default; it is never a promotion.
  for (const value of [null, undefined, '']) {
    assert.equal(permissionMode(value), 'workspace-write', String(value))
  }
  assert.equal(permissionMode('read-only'), 'read-only')
  assert.equal(permissionMode('full-access'), 'full-access')
})

// ----------------------------------------------------------------------- limits

test('the named limits keep their classic defaults', () => {
  assert.equal(MAX_FILE_BYTES, 10485760)
  assert.equal(MAX_USER_BYTES, 104857600)
  assert.equal(MAX_FILES, 8)
  assert.equal(MAX_CONTEXT_CHARS, 50000)
  assert.deepEqual(LIMITS, {
    maxFileBytes: MAX_FILE_BYTES,
    maxUserBytes: MAX_USER_BYTES,
    maxFiles: MAX_FILES,
    maxContextChars: MAX_CONTEXT_CHARS,
  })
})

test('one file is refused above the byte limit and accepted at it', () => {
  // The classic compares with ">", so the limit itself is inclusive.
  assert.equal(checkFileBytes({ bytes: MAX_FILE_BYTES, limits: LIMITS }).allowed, true)
  assert.equal(checkFileBytes({ bytes: MAX_FILE_BYTES - 1, limits: LIMITS }).allowed, true)
  assert.deepEqual(checkFileBytes({ bytes: MAX_FILE_BYTES + 1, limits: LIMITS }), { allowed: false, reason: 'ATTACHMENT_SIZE_LIMIT' })
  // An empty upload is a bad upload, never a stored zero-byte attachment.
  assert.equal(checkFileBytes({ bytes: 0, limits: LIMITS }).allowed, false)
})

test('the per-user budget refuses one byte over and accepts exactly at it', () => {
  const at = checkUserByteBudget({ usedBytes: MAX_USER_BYTES - 1, incomingBytes: 1, limits: LIMITS })
  assert.equal(at.allowed, true)
  assert.deepEqual(
    checkUserByteBudget({ usedBytes: MAX_USER_BYTES - 1, incomingBytes: 2, limits: LIMITS }),
    { allowed: false, reason: 'ATTACHMENT_STORAGE_LIMIT' },
  )
  assert.equal(checkUserByteBudget({ usedBytes: 0, incomingBytes: MAX_USER_BYTES, limits: LIMITS }).allowed, true)
  assert.equal(checkUserByteBudget({ usedBytes: MAX_USER_BYTES, incomingBytes: 1, limits: LIMITS }).allowed, false)
})

test('the file count and the context budget refuse past their limit and accept at it', () => {
  assert.equal(checkFileCount({ count: MAX_FILES, limits: LIMITS }).allowed, true)
  assert.deepEqual(checkFileCount({ count: MAX_FILES + 1, limits: LIMITS }), { allowed: false, reason: 'ATTACHMENT_COUNT_LIMIT' })
  assert.equal(checkContextChars({ chars: MAX_CONTEXT_CHARS, limits: LIMITS }).allowed, true)
  assert.deepEqual(checkContextChars({ chars: MAX_CONTEXT_CHARS + 1, limits: LIMITS }), { allowed: false, reason: 'ATTACHMENT_TEXT_LIMIT' })
})

test('a limit that cannot be evaluated refuses instead of becoming an unbounded allowance', () => {
  // NaN is the trap: every comparison against it is false, so a malformed limit
  // would otherwise disable the quota silently.
  const broken = { maxFileBytes: Number.NaN, maxUserBytes: Number.NaN, maxFiles: Number.NaN, maxContextChars: Number.NaN }
  assert.equal(checkFileBytes({ bytes: 1, limits: broken }).allowed, false)
  assert.equal(checkUserByteBudget({ usedBytes: 0, incomingBytes: 1, limits: broken }).allowed, false)
  assert.equal(checkFileCount({ count: 0, limits: broken }).allowed, false)
  assert.equal(checkContextChars({ chars: 0, limits: broken }).allowed, false)
  assert.equal(checkFileBytes({ bytes: 1, limits: { ...LIMITS, maxFileBytes: Number.POSITIVE_INFINITY } }).allowed, false)
  assert.equal(checkUserByteBudget({ usedBytes: -1, incomingBytes: 1, limits: LIMITS }).allowed, false)
})

// -------------------------------------------------------------------- retention

test('an abandoned upload is released only past the 24h window', () => {
  const nowMs = Date.parse('2026-09-21T00:00:00Z')
  assert.equal(STALE_UPLOAD_HOURS, 24)
  const decision = (createdAtMs, referenced = false, olderThanHours) =>
    staleUploadDecision({ createdAtMs, nowMs, referenced, olderThanHours })

  // Exactly on the boundary the upload is still being composed: kept.
  assert.deepEqual(decision(nowMs - 24 * HOUR_MS), { allowed: false, reason: 'ATTACHMENT_RECENT' })
  // One millisecond older is released.
  assert.equal(decision(nowMs - 24 * HOUR_MS - 1).allowed, true)
  assert.equal(decision(nowMs - 25 * HOUR_MS).allowed, true)
  // A referenced upload is evidence a message was sent with: never released.
  assert.deepEqual(decision(nowMs - 100 * HOUR_MS, true), { allowed: false, reason: 'ATTACHMENT_REFERENCED' })
  // A configurable window keeps the same strict comparison.
  assert.equal(decision(nowMs - 2 * HOUR_MS, false, 1).allowed, true)
  assert.equal(decision(nowMs - 2 * HOUR_MS, false, 3).allowed, false)
})

test('an unverifiable stale check keeps the bytes instead of freeing them', () => {
  // The failure direction is deliberate: keeping a stale upload costs allowance,
  // freeing a live one loses content.
  const kept = [
    { createdAtMs: 0, nowMs: Number.NaN, referenced: false },
    { createdAtMs: Number.NaN, nowMs: 1, referenced: false },
    { createdAtMs: 0, nowMs: 1, referenced: false, olderThanHours: Number.NaN },
    { createdAtMs: 0, nowMs: 1, referenced: false, olderThanHours: -1 },
  ]
  for (const input of kept) {
    assert.equal(staleUploadDecision(input).allowed, false, JSON.stringify(input))
  }
})

// -------------------------------------------------------------------- ownership

test('a row owned by another tenant is refused, and an unknown owner is not the same owner', () => {
  assert.equal(assertOwned('user-1', 'user-1').allowed, true)
  assert.deepEqual(assertOwned('user-1', 'user-2'), { allowed: false, reason: 'ATTACHMENT_NOT_FOUND' })
  // The refusal is deliberately indistinguishable from "no such row".
  assert.deepEqual(assertOwned('user-1', 'user-2').reason, assertOwned('user-1', '').reason)
  for (const [owner, row] of [['', 'user-1'], ['user-1', ''], [null, 'user-1'], ['user-1', undefined], [undefined, undefined]]) {
    assert.equal(assertOwned(owner, row).allowed, false, String(owner) + '/' + String(row))
  }
  // Ids are opaque: a padded id is not the id it pads.
  assert.equal(assertOwned('user-1', ' user-1').allowed, false)
  assert.equal(assertOwned('user-1', 'USER-1').allowed, false)
})

// ------------------------------------------------------------------ environment

test('limits come from the classic environment variables and a malformed one is refused', () => {
  assert.deepEqual(attachmentLimits({}), LIMITS)
  assert.equal(attachmentLimits({ AGENT_ATTACHMENT_MAX_BYTES: '1024' }).maxFileBytes, 1024)
  assert.equal(attachmentLimits({ AGENT_ATTACHMENT_USER_BYTES: '2048' }).maxUserBytes, 2048)
  assert.equal(attachmentLimits({ AGENT_ATTACHMENT_MAX_FILES: '2' }).maxFiles, 2)
  assert.equal(attachmentLimits({ AGENT_ATTACHMENT_MAX_BYTES: '' }).maxFileBytes, MAX_FILE_BYTES)
  for (const raw of ['2mb', '0', '-1', 'NaN', 'Infinity', '1.5']) {
    assert.throws(() => attachmentLimits({ AGENT_ATTACHMENT_MAX_BYTES: raw }), refusal('INVALID_ATTACHMENT_LIMIT'), raw)
  }
})

// ---------------------------------------------------------------- the provider

function fakeStore(overrides = {}) {
  return {
    permissionMode: async () => ({ found: true, mode: 'workspace-write' }),
    usedBytes: async () => 0,
    insertAttachment: async (row) => ({
      id: 'att-1', userId: row.userId, name: row.name, mime: row.mime, kind: row.kind,
      size: row.payload.byteLength, sha256: row.sha256, extractedText: row.extractedText, removed: false,
    }),
    attachment: async () => undefined,
    freeBytes: async () => 0,
    referencedAttachmentIds: async () => [],
    staleCandidates: async () => [],
    ...overrides,
  }
}

/** The provider only needs the two Context members it actually uses. */
function provider(store, config = {}, services = { pgAuth: { currentUser: async () => ({ id: 'user-1' }) } }) {
  return new TenantChatWorkspaceProvider({ reflect: { provide() {} }, get: (name) => services[name] }, config, store)
}

const upload = { name: 'notes.md', payload: new TextEncoder().encode('hello'), mime: 'text/markdown', kind: 'file' }

test('without authentication or storage the seam refuses rather than degrading', async () => {
  const anonymous = provider(fakeStore(), {}, {})
  await assert.rejects(anonymous.permissionMode('conv-1'), refusal('WORKSPACE_NOT_AUTHORIZED'))
  await assert.rejects(anonymous.saveAttachment(upload), refusal('WORKSPACE_NOT_AUTHORIZED'))

  const failing = provider(fakeStore(), {}, { pgAuth: { currentUser: async () => { throw new Error('no session') } } })
  await assert.rejects(failing.ownedAttachment('att-1'), refusal('WORKSPACE_NOT_AUTHORIZED'))

  // Registered but unconfigured storage: no conversation mode, no uploads.
  const unconfigured = provider(undefined)
  await assert.rejects(unconfigured.permissionMode('conv-1'), refusal('WORKSPACE_STORE_UNAVAILABLE'))
  await assert.rejects(unconfigured.saveAttachment(upload), refusal('WORKSPACE_STORE_UNAVAILABLE'))
  await assert.rejects(unconfigured.resolveAttachments([]), refusal('WORKSPACE_STORE_UNAVAILABLE'))
})

test('a conversation this user does not own is refused, not given a default mode', async () => {
  const missing = provider(fakeStore({ permissionMode: async () => ({ found: false, mode: null }) }))
  await assert.rejects(missing.permissionMode('conv-1'), refusal('CONVERSATION_NOT_FOUND'))
  await assert.rejects(missing.toolPermission('conv-1', 'get_market_quote'), refusal('CONVERSATION_NOT_FOUND'))
  await assert.rejects(missing.permissionMode(''), refusal('CONVERSATION_NOT_FOUND'))
})

test('the stored mode decides the tool, and a mode nobody recognises is refused', async () => {
  const readOnly = provider(fakeStore({ permissionMode: async () => ({ found: true, mode: 'read-only' }) }))
  assert.equal(await readOnly.permissionMode('conv-1'), 'read-only')
  assert.equal(await readOnly.toolPermission('conv-1', 'get_market_quote'), 'allow')
  assert.equal(await readOnly.toolPermission('conv-1', 'place_order'), 'deny')

  const full = provider(fakeStore({ permissionMode: async () => ({ found: true, mode: 'full-access' }) }))
  assert.equal(await full.toolPermission('conv-1', 'place_order'), 'allow')

  // A NULL column is the classic "never chose one".
  const unset = provider(fakeStore({ permissionMode: async () => ({ found: true, mode: null }) }))
  assert.equal(await unset.permissionMode('conv-1'), 'workspace-write')

  const corrupted = provider(fakeStore({ permissionMode: async () => ({ found: true, mode: 'yolo' }) }))
  await assert.rejects(corrupted.toolPermission('conv-1', 'get_market_quote'), refusal('INVALID_PERMISSION_MODE'))
})

test('a row the storage hands back for another owner is refused', async () => {
  const foreign = { id: 'att-1', userId: 'user-2', name: 'x', mime: 'text/plain', kind: 'file', size: 3, sha256: 's', extractedText: 'x', removed: false }
  const store = fakeStore({ attachment: async () => foreign })
  await assert.rejects(provider(store).ownedAttachment('att-1'), refusal('ATTACHMENT_NOT_FOUND'))
  await assert.rejects(provider(store).resolveAttachments([{ id: 'att-1' }]), refusal('ATTACHMENT_NOT_FOUND'))
  // An ownerless row is unverifiable, so it is refused too.
  const ownerless = fakeStore({ attachment: async () => ({ ...foreign, userId: '' }) })
  await assert.rejects(provider(ownerless).ownedAttachment('att-1'), refusal('ATTACHMENT_NOT_FOUND'))
})

test('an upload is refused above the configured byte limit and never stored', async () => {
  let inserted = 0
  const store = fakeStore({ insertAttachment: async (row) => { inserted += 1; return { id: 'att-1', userId: row.userId, name: row.name, mime: row.mime, kind: row.kind, size: row.payload.byteLength, sha256: row.sha256, extractedText: row.extractedText, removed: false } } })
  const workspace = provider(store, { maxFileBytes: 4 })
  await assert.rejects(workspace.saveAttachment(upload), refusal('ATTACHMENT_SIZE_LIMIT'))
  assert.equal(inserted, 0)

  const saved = await provider(store, { maxFileBytes: 5 }).saveAttachment(upload)
  assert.equal(saved.size, 5)
  assert.equal(saved.name, 'notes.md')
  assert.equal(saved.removed, false)
  assert.equal(saved.url, '/api/agent/attachments/att-1/content')
  assert.match(saved.sha256, /^[0-9a-f]{64}$/)
})

test('a full allowance releases abandoned uploads before it refuses the new one', async () => {
  const nowMs = Date.now()
  let used = MAX_USER_BYTES
  const freed = []
  const store = fakeStore({
    usedBytes: async () => used,
    staleCandidates: async () => [{ id: 'abandoned', createdAtMs: nowMs - 25 * HOUR_MS }, { id: 'recent', createdAtMs: nowMs - HOUR_MS }],
    referencedAttachmentIds: async () => ['sent'],
    freeBytes: async (_userId, ids) => {
      freed.push(...ids)
      used -= ids.length * (MAX_USER_BYTES / 2)
      return ids.length
    },
  })
  const saved = await provider(store).saveAttachment(upload)
  // Only the unreferenced, genuinely old upload is reclaimed.
  assert.deepEqual(freed, ['abandoned'])
  assert.equal(saved.size, 5)
  // The reclaim predicate is re-applied by the seam, not trusted from the storage.
  assert.equal(freed.includes('recent'), false)
  assert.equal(freed.includes('sent'), false)
})

test('a quota that stays full after the reclaim refuses the upload', async () => {
  const store = fakeStore({ usedBytes: async () => MAX_USER_BYTES, staleCandidates: async () => [] })
  await assert.rejects(provider(store).saveAttachment(upload), refusal('ATTACHMENT_STORAGE_LIMIT'))
})

test('freeing a conversation releases only the bytes its own messages carry', async () => {
  const asked = []
  const store = fakeStore({
    referencedAttachmentIds: async (userId, conversationId) => { asked.push([userId, conversationId]); return ['att-1', 'att-2'] },
    freeBytes: async (userId, ids) => { asked.push([userId, ids]); return ids.length },
  })
  assert.equal(await provider(store).releaseConversationAttachments('conv-1'), 2)
  assert.deepEqual(asked, [['user-1', 'conv-1'], ['user-1', ['att-1', 'att-2']]])

  const empty = provider(fakeStore({ referencedAttachmentIds: async () => [] }))
  assert.equal(await empty.releaseConversationAttachments('conv-1'), 0)
})

test('removing an attachment keeps the record and drops the bytes and the URL', async () => {
  const row = { id: 'att-1', userId: 'user-1', name: 'notes.md', mime: 'text/markdown', kind: 'file', size: 5, sha256: 's', extractedText: 'hello', removed: false }
  const store = fakeStore({ attachment: async () => row, freeBytes: async () => 1 })
  const removed = await provider(store).removeAttachment('att-1')
  assert.equal(removed.removed, true)
  assert.equal(removed.url, '')
  assert.equal(removed.name, 'notes.md')
  assert.equal(removed.size, 0)

  // A row that is already gone is a refusal, not a success.
  await assert.rejects(provider(fakeStore({ freeBytes: async () => 0 })).removeAttachment('att-1'), refusal('ATTACHMENT_NOT_FOUND'))
  await assert.rejects(provider(fakeStore({ freeBytes: async () => 0 })).removeAttachment(''), refusal('ATTACHMENT_NOT_FOUND'))
})

test('resolving a turn drops freed and missing attachments and refuses an oversized turn', async () => {
  const row = { id: 'att-1', userId: 'user-1', name: 'notes.md', mime: 'text/markdown', kind: 'file', size: 5, sha256: 's', extractedText: 'hello', removed: false }
  const store = fakeStore({ attachment: async (userId, id) => (id === 'att-1' ? row : id === 'freed' ? { ...row, id: 'freed', size: 0, extractedText: '', removed: true } : undefined) })
  const workspace = provider(store)

  const resolved = await workspace.resolveAttachments([{ id: 'att-1' }, { id: 'missing' }, { id: 'freed' }, { name: 'inline', content: 'text' }])
  assert.equal(resolved.length, 2)
  assert.equal(resolved[0].content, 'hello')
  assert.equal(resolved[0].url, '/api/agent/attachments/att-1/content')
  assert.deepEqual(resolved[1], { name: 'inline', mime: 'text/plain', content: 'text' })

  // Trust boundary: a stored turn is not a typed payload.
  await assert.rejects(workspace.resolveAttachments(['not-an-object']), refusal('ATTACHMENT_INVALID'))
  await assert.rejects(workspace.resolveAttachments([{ name: 'x', content: 'y'.repeat(20_001) }]), refusal('ATTACHMENT_TEXT_LIMIT'))
  await assert.rejects(workspace.resolveAttachments([{ name: 'x', content: 'y'.repeat(MAX_CONTEXT_CHARS + 1) }]), refusal('ATTACHMENT_TEXT_LIMIT'))

  const oneFile = provider(store, { maxFiles: 1 })
  await assert.rejects(oneFile.resolveAttachments([{ id: 'att-1' }, { id: 'missing' }]), refusal('ATTACHMENT_COUNT_LIMIT'))
})

test('an upload with no usable name is refused and a hostile one is sanitized', async () => {
  const workspace = provider(fakeStore())
  for (const name of ['', '\u0000\u0001', 42, null]) {
    await assert.rejects(workspace.saveAttachment({ ...upload, name }), refusal('ATTACHMENT_INVALID'), JSON.stringify(name))
  }
  // The classic keeps the last path component, drops control characters and
  // bounds the name to 160 characters.
  assert.equal((await workspace.saveAttachment({ ...upload, name: '../../etc/passwd' })).name, 'passwd')
  assert.equal((await workspace.saveAttachment({ ...upload, name: 'a\u0000b.txt' })).name, 'ab.txt')
  assert.equal((await workspace.saveAttachment({ ...upload, name: 'x'.repeat(200) })).name.length, 160)
})
