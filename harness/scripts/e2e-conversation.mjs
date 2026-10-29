// End-to-end conversation scenarios on two paths, side by side:
//   DSH  — browser-equivalent calls through the session broker to a real
//          per-user DSH Web Host (@deepseek-ai/dsh 0.1.7-rc.1, PureGamma
//          profile + multi-tenant overlay), whose legacy-api providers call a
//          real local FastAPI with the user's Host token;
//   legacy — the FastAPI Web agent path (/api/agent/*) the Next.js chat uses.
// Both talk to the same model endpoint.
//
// Default (E2E_MODEL=mock): a deterministic OpenAI/Anthropic-compatible mock
// on 127.0.0.1 (scripts/fixtures/mock-llm.mjs); nothing leaves the machine
// (DSH telemetry is disabled, the API's model base URL is overridden).
// E2E_MODEL=real: no mock; the model endpoint and key come from
// DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY for both paths, and assertions that
// depend on the mock's exact wording are relaxed. Use it on staging with a
// real key; its results are labelled as such.
//
//   PUREGAMMA_DSH_BIN=/abs/@deepseek-ai/dsh/lib/bin.js \
//     pnpm --dir harness exec tsx scripts/e2e-conversation.mjs
//
// Writes $E2E_OUT (default /var/tmp/pgws-e2e)/report.{json,md}.
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { randomBytes, randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { createBroker, defaultContentSecurityPolicy, loadConfig } from '../packages/session-broker/src/index.ts'
import { startMockLlm } from './fixtures/mock-llm.mjs'

const harness = process.cwd()
const repo = path.resolve(harness, '..')
const dshBin = process.env.PUREGAMMA_DSH_BIN
if (!dshBin || !existsSync(dshBin)) {
  console.error('set PUREGAMMA_DSH_BIN to the pinned DSH launcher (lib/bin.js)')
  process.exit(2)
}
const MODEL = process.env.E2E_MODEL === 'real' ? 'real' : 'mock'
const python = process.env.E2E_PYTHON ?? '/var/tmp/pgvenv/bin/python'
const out = process.env.E2E_OUT ?? '/var/tmp/pgws-e2e'
const apiPort = Number(process.env.E2E_API_PORT ?? 3131)
const brokerPort = Number(process.env.E2E_BROKER_PORT ?? 3132)
const legacyApproval = process.env.E2E_LEGACY_APPROVAL_WRAPPER !== '0'
mkdirSync(out, { recursive: true })
const root = mkdtempSync(path.join(process.env.E2E_TMP ?? tmpdir(), 'pg-e2e-'))
const SECRET = randomBytes(24).toString('hex')
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

/** `ws` ships with DSH; resolve it from the pinned install. */
function loadWs() {
  const pnpm = dshBin.slice(0, dshBin.indexOf('/node_modules/') + '/node_modules/'.length) + '.pnpm'
  const dir = readdirSync(pnpm).find(entry => /^ws@8\./.test(entry))
  return createRequire(path.join(pnpm, dir, 'node_modules', 'ws', 'package.json'))('ws')
}
const WebSocket = loadWs()

// ── services ────────────────────────────────────────────────────────────────
const children = []
async function waitFor(url, ms = 90_000) {
  const until = Date.now() + ms
  while (Date.now() < until) {
    try { if ((await fetch(url)).ok) return } catch {}
    await sleep(500)
  }
  throw new Error(`${url} did not come up`)
}

const mock = MODEL === 'mock' ? await startMockLlm(0) : undefined
const modelBase = mock?.url ?? process.env.DEEPSEEK_BASE_URL?.replace(/\/v1\/?$/, '')
const modelKey = mock ? 'sk-local-mock' : process.env.DEEPSEEK_API_KEY
if (!modelBase || !modelKey) throw new Error('E2E_MODEL=real needs DEEPSEEK_BASE_URL and DEEPSEEK_API_KEY')

// The legacy API's database. SQLite (default) serialises writers: a reply
// stream holds the write lock, so a concurrent cancel waits out the 5 s busy
// timeout and fails. E2E_POSTGRES=docker runs a throwaway postgres:17
// container (loopback port, removed at the end) like production.
let databaseUrl = `sqlite:///${path.join(root, 'api.db')}`
let pgContainer
if (process.env.E2E_POSTGRES === 'docker') {
  const pgPort = Number(process.env.E2E_POSTGRES_PORT ?? 3133)
  const password = randomBytes(12).toString('hex')
  pgContainer = `pg-e2e-${randomBytes(3).toString('hex')}`
  execFileSync('docker', ['run', '-d', '--rm', '--name', pgContainer, '--label', 'puregamma.e2e=1', '-p', `127.0.0.1:${pgPort}:5432`,
    '-e', `POSTGRES_PASSWORD=${password}`, '-e', 'POSTGRES_USER=puregamma', '-e', 'POSTGRES_DB=puregamma', '--memory', '256m', 'postgres:17'], { stdio: 'ignore' })
  for (let i = 0; i < 60; i++) {
    try { execFileSync('docker', ['exec', pgContainer, 'pg_isready', '-U', 'puregamma'], { stdio: 'ignore' }); break } catch { await sleep(1000) }
  }
  await sleep(1500)
  databaseUrl = `postgresql+psycopg://puregamma:${password}@127.0.0.1:${pgPort}/puregamma`
}
const sql = statement => execFileSync(python, ['-c', `import sqlalchemy as sa, sys; e=sa.create_engine(sys.argv[1]); c=e.connect(); r=c.execute(sa.text(sys.argv[2])); c.commit(); print(r.fetchone()[0] if r.returns_rows else '')`, databaseUrl, statement], { encoding: 'utf8' }).trim()
const apiUrl = `http://127.0.0.1:${apiPort}`
const brokerOrigin = `http://127.0.0.1:${brokerPort}`
const apiEnv = {
  PATH: process.env.PATH, HOME: root, PYTHONPATH: repo,
  APP_ENV: 'development',
  DATABASE_URL: databaseUrl,
  JWT_SECRET: randomBytes(24).toString('hex'), SESSION_SECRET: randomBytes(24).toString('hex'),
  SITE_URL: brokerOrigin,
  LLM_PROVIDER: 'deepseek', DEEPSEEK_API_KEY: modelKey, DEEPSEEK_BASE_URL: `${modelBase}/v1`,
  CREDIT_USAGE_ENFORCED: 'false', ENABLE_MOCK_MARKET_DATA: 'true', SENTRY_DSN: '',
  DSH_MULTI_TENANT_ENABLED: 'true', DSH_BROKER_SECRET: SECRET,
  DSH_BROKER_REVOKE_URL: `${brokerOrigin}/__broker/revoke`,
}
// The shipped API classifies no tool as stateful, so its approval flow can
// never fire; this test-only wrapper marks one tool stateful to show how the
// legacy flow behaves. The report labels these results.
const serve = `import uvicorn${legacyApproval ? "\nimport apps.api.services.chat_workspace as cw\ncw.STATEFUL_TOOLS = frozenset({'create_strategy_draft'})" : ''}\nuvicorn.run('apps.api.main:app', host='127.0.0.1', port=${apiPort}, log_level='info')`
const apiLog = (await import('node:fs')).openSync(path.join(out, 'api.log'), 'w')
const api = spawn(python, ['-c', serve], { cwd: repo, env: apiEnv, stdio: ['ignore', apiLog, apiLog], detached: true })
children.push(api)
await waitFor(`${apiUrl}/health`)

// The broker passes these to the Host: model endpoint + key, telemetry off.
process.env.DEEPSEEK_BASE_URL = modelBase
process.env.DEEPSEEK_API_KEY = modelKey
process.env.DSH_TELEMETRY_MODE = 'DISABLED'
const config = {
  ...loadConfig({}),
  enabled: true,
  publicOrigin: brokerOrigin,
  contentSecurityPolicy: defaultContentSecurityPolicy(brokerOrigin),
  apiBaseUrl: apiUrl, hostApiBaseUrl: apiUrl, brokerSecret: SECRET,
  hostsRoot: path.join(root, 'hosts'), dshBin,
  profileDir: path.join(harness, 'profile'), patchFiles: [path.join(harness, 'profile', 'multi-tenant.patch.yml')],
  maxHosts: 2, startTimeoutMs: 180_000, hostHeapMb: Number(process.env.E2E_HOST_HEAP_MB ?? 512),
  envPassthrough: ['DEEPSEEK_BASE_URL', 'DEEPSEEK_API_KEY', 'DSH_TELEMETRY_MODE'],
  audit: path.join(root, 'audit.jsonl'), instance: `e2e${randomBytes(2).toString('hex')}`,
}
const broker = createBroker(config, { log: message => console.log(`  [broker] ${message}`) })
await new Promise(resolve => broker.server.listen(brokerPort, '127.0.0.1', resolve))

async function cleanup() {
  await broker.close().catch(() => {})
  await mock?.close().catch(() => {})
  for (const child of children) { try { process.kill(-child.pid, 'SIGTERM') } catch {} }
  if (pgContainer) { try { execFileSync('docker', ['rm', '-f', pgContainer], { stdio: 'ignore' }) } catch {} }
  if (process.env.E2E_KEEP !== '1') rmSync(root, { recursive: true, force: true })
}

// ── a signed-in test user (local only) ─────────────────────────────────────
const login = await fetch(`${apiUrl}/auth/mock-login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: 'e2e@example.invalid', name: 'E2E', locale: 'en' }) })
assert.equal(login.status, 200, 'mock-login')
const pgSession = /pg_session=([^;]+)/.exec(login.headers.get('set-cookie') ?? '')?.[1]
assert.ok(pgSession, 'session cookie')
// Free plan allows 5 runs a day; this run needs more.
sql("update users set plan='Enterprise' where email='e2e@example.invalid'")
const cookie = `pg_session=${pgSession}`

// ── DSH client (through the broker, like the browser) ──────────────────────
let rpcId = 0
async function rpc(endpoint, args) {
  const response = await fetch(`${brokerOrigin}/api/${endpoint}`, {
    method: 'POST',
    headers: { cookie, origin: brokerOrigin, 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: String(++rpcId), method: endpoint, payload: { args } }),
  })
  const body = await response.json().catch(() => null)
  if (response.status !== 200) throw new Error(`${endpoint} HTTP ${response.status} ${JSON.stringify(body)}`)
  if (!body?.result?.ok) throw Object.assign(new Error(`${endpoint}: ${JSON.stringify(body?.result?.error ?? body)}`), { error: body?.result?.error })
  return body.result.value
}
async function sessionEvents(sessionId) {
  const projections = await rpc('session/projections', { request: { sessionId } })
  if (!projections) return []
  const page = await rpc('session/page', { request: { address: { kind: 'session', sessionId }, throughSeq: projections.asOfSeq, maxMessages: 200 } })
  return page.records.filter(record => record.type === 'event').map(record => record.event)
}
const turnEnds = events => events.filter(event => event.type === 'turn/end')
async function waitTurns(sessionId, count, ms = 120_000) {
  const until = Date.now() + ms
  while (Date.now() < until) {
    const events = await sessionEvents(sessionId)
    if (turnEnds(events).length >= count) return events
    await sleep(400)
  }
  throw new Error(`session did not reach ${count} completed turn(s)`)
}
const replies = events => events.filter(event => event.type === 'assistant/message')
  .map(event => (event.data?.message?.content ?? []).filter(part => part.type === 'text').map(part => part.text).join(''))
  .filter(Boolean)
const prompt = (sessionId, content) => rpc('session/prompt', { request: { requestId: randomUUID(), sessionId, mode: 'queue', content: typeof content === 'string' ? [{ type: 'text', text: content }] : content, clientTimeZone: 'UTC' } })
const newSession = async () => (await rpc('session/create', { request: {} })).sessionId

/** The Remote stream mux, as the browser opens it. */
function openMux() {
  const ws = new WebSocket(`ws://127.0.0.1:${brokerPort}/api/remote.mux`, { headers: { cookie, origin: brokerOrigin } })
  const items = []
  const waiters = []
  ws.on('message', data => {
    const frame = JSON.parse(String(data))
    items.push(frame)
    for (const waiter of [...waiters]) if (waiter.test(frame)) { waiters.splice(waiters.indexOf(waiter), 1); waiter.resolve(frame) }
  })
  const opened = new Promise((resolve, reject) => { ws.once('open', resolve); ws.once('error', reject); ws.once('unexpected-response', (_req, res) => reject(new Error(`mux HTTP ${res.statusCode}`))) })
  return {
    ws, items, opened,
    send: frame => ws.send(JSON.stringify(frame)),
    next: (test, ms = 60_000) => {
      const hit = items.find(test)
      if (hit) return Promise.resolve(hit)
      return new Promise((resolve, reject) => {
        const waiter = { test, resolve }
        waiters.push(waiter)
        setTimeout(() => reject(new Error('mux frame timeout')), ms).unref()
      })
    },
    close: () => new Promise(resolve => { ws.once('close', resolve); ws.terminate() }),
  }
}

// ── legacy client (FastAPI /api/agent/*) ────────────────────────────────────
async function legacy(method, pathname, body, raw) {
  const response = await fetch(`${apiUrl}/api/agent${pathname}`, {
    method, headers: { cookie, ...(body && !raw ? { 'content-type': 'application/json' } : {}) },
    body: raw ?? (body ? JSON.stringify(body) : undefined),
  })
  const text = await response.text()
  let parsed = null
  try { parsed = JSON.parse(text) } catch {}
  return { status: response.status, body: parsed, text }
}
/** POST a message and read its SSE stream; `onEvent` may return 'stop' to drop the connection. */
async function legacySend(conversationId, content, extra = {}, onEvent = () => {}) {
  const controller = new AbortController()
  const response = await fetch(`${apiUrl}/api/agent/conversations/${conversationId}/messages`, {
    method: 'POST', signal: controller.signal,
    headers: { cookie, 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify({ content, client_request_id: `e2e-${randomUUID()}`, locale: 'en', research_mode: true, data_sources: [], skills: [], skill_refs: [], custom_prompt: '', attachments: [], model: 'default', ...extra }),
  })
  const events = []
  if (response.status !== 200) return { status: response.status, events, body: await response.text() }
  const decoder = new TextDecoder()
  let buffer = ''
  let aborted = false
  try {
    for await (const chunk of response.body) {
      buffer += decoder.decode(chunk, { stream: true })
      let index
      while ((index = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, index)
        buffer = buffer.slice(index + 2)
        const type = /^event: (.+)$/m.exec(block)?.[1]
        const data = /^data: (.+)$/m.exec(block)?.[1]
        if (!type) continue
        const event = { type, data: data ? JSON.parse(data) : {} }
        events.push(event)
        if (await onEvent(event) === 'stop') {
          aborted = true
          controller.abort()
          break
        }
      }
      if (aborted) break
    }
  } catch (error) {
    if (error.name !== 'AbortError') throw error
  }
  return { status: 200, events, aborted }
}
const legacyReply = events => events.filter(event => event.type === 'message.delta').map(event => event.data.delta).join('')
const newConversation = async () => (await legacy('POST', '/conversations', { title: null })).body.conversation.id
const mockRequests = () => mock ? mock.requests : []
const lastRequestWith = predicate => [...mockRequests()].reverse().find(predicate)

// ── scenarios ───────────────────────────────────────────────────────────────
const results = []
const only = process.env.E2E_ONLY ? new Set(process.env.E2E_ONLY.split(',')) : undefined
async function scenario(id, title, { dsh, legacy: legacyRun, compare }) {
  if (only && !only.has(id)) return
  const row = { id, title, dsh: { status: 'fail', note: '' }, legacy: { status: 'fail', note: '' }, comparison: '' }
  for (const [side, run] of [['dsh', dsh], ['legacy', legacyRun]]) {
    try {
      const note = await run()
      row[side] = typeof note === 'object' && note?.status ? note : { status: 'pass', note: note ?? '' }
    } catch (error) {
      row[side] = { status: 'fail', note: String(error?.message ?? error).slice(0, 400) }
    }
    console.log(`${row[side].status === 'pass' ? 'ok' : row[side].status} - [${side}] ${title}${row[side].note ? `: ${row[side].note}` : ''}`)
  }
  row.comparison = compare(row)
  results.push(row)
}
const exact = (actual, expected) => MODEL === 'real' ? assert.ok(actual.length > 0, 'non-empty reply') : assert.equal(actual, expected)

const dshState = {}
const legacyState = {}

try {
  await scenario('new', '新建对话并得到回复', {
    async dsh() {
      dshState.session = await newSession()
      await prompt(dshState.session, 'hello e2e')
      const events = await waitTurns(dshState.session, 1)
      exact(replies(events).at(-1), 'Echo: hello e2e')
      assert.equal(turnEnds(events)[0].data.reason.kind, 'completed')
      return `reply "${replies(events).at(-1)}"`
    },
    async legacy() {
      legacyState.conversation = await newConversation()
      const run = await legacySend(legacyState.conversation, 'hello e2e')
      assert.ok(run.events.some(event => event.type === 'message.completed'), JSON.stringify(run.events.map(event => event.type)))
      exact(legacyReply(run.events), 'Echo: hello e2e')
      return `reply "${legacyReply(run.events)}"`
    },
    compare: () => '相同：两条路径都把用户消息发给同一模型并返回同一回复',
  })

  await scenario('continue', '继续对话（模型收到历史）', {
    async dsh() {
      await prompt(dshState.session, 'second turn')
      const events = await waitTurns(dshState.session, 2)
      exact(replies(events).at(-1), 'Echo: second turn')
      const request = lastRequestWith(item => item.lastUser.includes('second turn'))
      if (mock) assert.ok(request.turns >= 3, `model saw ${request?.turns} turns`)
      return `reply "${replies(events).at(-1)}", model saw ${request?.turns ?? '?'} turns`
    },
    async legacy() {
      const run = await legacySend(legacyState.conversation, 'second turn')
      exact(legacyReply(run.events), 'Echo: second turn')
      const request = lastRequestWith(item => item.lastUser.includes('second turn') && item.stream)
      if (mock) assert.ok(request.turns >= 3, `model saw ${request?.turns} turns`)
      return `reply "${legacyReply(run.events)}", model saw ${request?.turns ?? '?'} turns`
    },
    compare: () => '相同：历史随下一轮发送给模型（轮数因各自的系统提示结构不同而不同）',
  })

  await scenario('refresh', '刷新恢复（含进行中的回复）', {
    async dsh() {
      await prompt(dshState.session, '[[slow]] long answer')
      await sleep(1500)
      // A fresh client with no local state: what a reload sees.
      const listed = await rpc('session/list', { _request: {} })
      assert.ok(JSON.stringify(listed).includes(dshState.session))
      const midway = await sessionEvents(dshState.session)
      assert.ok(midway.some(event => event.type === 'user/message' && JSON.stringify(event.data).includes('long answer')), 'pending user message is durable')
      assert.equal(turnEnds(midway).length, 2, 'turn still running')
      const done = await waitTurns(dshState.session, 3)
      if (mock) assert.match(replies(done).at(-1), /part40$/)
      return 'mid-turn reload shows the durable user message and an open turn; full reply after completion'
    },
    async legacy() {
      let runId
      const pending = legacySend(legacyState.conversation, '[[slow]] long answer', {}, event => { if (event.type === 'run.started') runId = event.data.runId })
      await sleep(2500)
      const midway = await legacy('GET', `/conversations/${legacyState.conversation}`)
      assert.equal(midway.status, 200)
      assert.ok(midway.body.active_run_id, 'active run visible on reload')
      const streaming = midway.body.messages.at(-1)
      const run = await pending
      const after = await legacy('GET', `/conversations/${legacyState.conversation}`)
      if (mock) assert.match(after.body.messages.at(-1).content, /part40$/)
      return `reload mid-run: active_run_id set, last message status "${streaming?.status}", content length ${streaming?.content?.length ?? 0}; run ${runId ? 'id seen' : '?'}, ${run.events.length} events`
    },
    compare: row => row.dsh.status === 'pass' && row.legacy.status === 'pass'
      ? '不同：DSH 刷新后可以通过 follow 快照继续看到正在生成的回复；旧路径刷新时只看到 streaming 状态和空内容（增量未提交），要等回复结束才能看到全文'
      : '见各自备注',
  })

  await scenario('cancel', '取消正在生成的回复', {
    async dsh() {
      const session = await newSession()
      await prompt(session, '[[slow]] please cancel me')
      await sleep(2000)
      await rpc('session/cancel', { request: { sessionId: session } })
      const events = await waitTurns(session, 1, 30_000)
      assert.equal(turnEnds(events)[0].data.reason.kind, 'aborted')
      return `turn ended "${turnEnds(events)[0].data.reason.kind}"`
    },
    async legacy() {
      const conversation = await newConversation()
      let canceled
      const run = await legacySend(conversation, '[[slow]] please cancel me', {}, async event => {
        if (event.type === 'run.started') {
          setTimeout(async () => {
            const began = Date.now()
            canceled = await legacy('POST', `/runs/${event.data.runId}/cancel`)
            canceled.ms = Date.now() - began
          }, 2000)
        }
      })
      assert.ok(canceled, 'cancel was sent')
      assert.equal(canceled.status, 200, `cancel HTTP ${canceled.status} after ${canceled.ms} ms: ${canceled.text.slice(0, 200)}`)
      assert.ok(run.events.some(event => event.type === 'run.canceled'), JSON.stringify(run.events.map(event => event.type)))
      return 'run.canceled emitted'
    },
    compare: row => row.dsh.status === 'pass' && row.legacy.status === 'pass' ? '相同：取消后回合结束（DSH `aborted` / 旧路径 `run.canceled`）' : '不同：见备注',
  })

  await scenario('reconnect', '断线重连（回复进行中断开再连）', {
    async dsh() {
      const session = await newSession()
      const first = openMux()
      await first.opened
      first.send({ type: 'open', streamId: 'f1', endpoint: 'session/follow', payload: { args: { request: { address: { kind: 'session', sessionId: session }, assistantStream: true } } } })
      await first.next(frame => frame.type === 'item' && frame.value?.type === 'snapshot')
      await prompt(session, '[[slow]] survive a disconnect')
      await first.next(frame => frame.type === 'item' && frame.value?.type === 'assistant-stream' && frame.value.frame?.type === 'chunk')
      await first.close()
      await sleep(1000)
      const second = openMux()
      await second.opened
      second.send({ type: 'open', streamId: 'f2', endpoint: 'session/follow', payload: { args: { request: { address: { kind: 'session', sessionId: session }, assistantStream: true } } } })
      const snapshot = await second.next(frame => frame.type === 'item' && frame.value?.type === 'snapshot')
      const ended = await second.next(frame => frame.type === 'item' && frame.value?.type === 'event' && frame.value.event?.type === 'turn/end', 90_000)
      await second.close()
      assert.equal(ended.value.event.data.reason.kind, 'completed', 'the turn kept running while disconnected')
      const events = await sessionEvents(session)
      if (mock) assert.match(replies(events).at(-1), /part40$/)
      return `resumed via a new follow (snapshot ${snapshot.value.records?.length ?? 0} records), turn completed with the full reply`
    },
    async legacy() {
      const conversation = await newConversation()
      let runId
      const run = await legacySend(conversation, '[[slow]] survive a disconnect', {}, event => {
        if (event.type === 'run.started') runId = event.data.runId
        if (event.type === 'message.delta') return 'stop'
      })
      assert.ok(run.aborted && runId, `stream HTTP ${run.status} ${String(run.body ?? '').slice(0, 200)} events ${run.events.map(event => event.type).join(',')}`)
      const early = (await legacy('GET', `/runs/${runId}/events?after=0`)).body.status
      let replay
      for (let i = 0; i < 60; i++) {
        replay = await legacy('GET', `/runs/${runId}/events?after=0`)
        if (!['pending', 'running'].includes(replay.body.status)) break
        await sleep(1000)
      }
      assert.equal(replay.status, 200)
      const after = await legacy('GET', `/conversations/${conversation}`)
      const last = after.body.messages.at(-1)
      return { status: 'pass', note: `right after the disconnect the run is "${early}", it settles as "${replay.body.status}"; replay has ${replay.body.events.length} stored events (deltas are not stored); last message status "${last?.status}", ${last?.content?.length ?? 0} chars` }
    },
    compare: row => /settles as "interrupted"/.test(row.legacy.note)
      ? '不同：DSH 断线不影响回合，重连后由 follow 快照继续收到完整回复；旧路径断线后运行被结算为 interrupted，回复不完整，只能回放已存储的事件（不含增量文本）'
      : /settles as "completed"/.test(row.legacy.note)
        ? '不同：旧路径断线后服务端继续生成并完成，但客户端无法重新接入流（增量不存储），只能等完成后重新加载；DSH 重连后由 follow 快照继续'
        : '见备注',
  })

  await scenario('archive', '归档 / 取消归档', {
    async dsh() {
      const session = await newSession()
      await prompt(session, 'to be archived')
      await waitTurns(session, 1)
      const archived = await rpc('workspace/archiveSession', { request: { sessionId: session } })
      assert.deepEqual(archived.archivedSessionIds, [session])
      await prompt(session, 'after archive')
      const events = await waitTurns(session, 2)
      assert.equal(turnEnds(events)[1].data.reason.kind, 'blocked', 'archived Sessions do not call the model')
      assert.ok(!mockRequests().some(item => item.lastUser.includes('after archive')) || !mock, 'no model request')
      await rpc('workspace/unarchiveSession', { request: { sessionId: session } })
      await prompt(session, 'after unarchive')
      const again = await waitTurns(session, 3)
      exact(replies(again).at(-1), 'Echo: after unarchive')
      return 'archived prompt ends "blocked" without a model call; unarchive restores'
    },
    async legacy() {
      const conversation = await newConversation()
      await legacySend(conversation, 'to be archived')
      const archived = await legacy('PATCH', `/conversations/${conversation}`, { archived: true })
      assert.equal(archived.status, 200)
      assert.ok(archived.body.conversation.archived_at)
      const run = await legacySend(conversation, 'after archive')
      const answered = run.events.some(event => event.type === 'message.completed')
      const restored = await legacy('PATCH', `/conversations/${conversation}`, { archived: false })
      assert.equal(restored.body.conversation.archived_at, null)
      return `archived_at set/cleared; a message to an archived conversation is ${answered ? 'still answered' : 'refused'}`
    },
    compare: row => /still answered/.test(row.legacy.note) ? '不同：DSH 归档后拒绝新回合（blocked）；旧路径归档只是列表标记，仍会回答' : '见备注',
  })

  await scenario('skill', 'Skill', {
    async dsh() {
      const session = await newSession()
      const skills = await rpc('skills/list', { request: { sessionId: session } })
      assert.ok(JSON.stringify(skills).includes('market-research'), 'market-research listed')
      await prompt(session, '/market-research check BTC')
      const events = await waitTurns(session, 1)
      const injected = events.find(event => event.type === 'user/message' && event.data?.source?.kind === 'skill-invocation')
      assert.ok(injected, `skill-invocation message in the log: ${JSON.stringify(events.map(event => event.type))}`)
      assert.equal(injected.data.source.name, 'market-research')
      if (mock) assert.ok(mockRequests().some(item => item.corpus?.includes('Build the current-market evidence pack')), 'SKILL.md body reached the model')
      return 'slash command injected the SKILL.md body as a skill-invocation message; model received it'
    },
    async legacy() {
      const conversation = await newConversation()
      const caps = await legacy('GET', '/capabilities')
      assert.ok(caps.body.skills.some(skill => skill.slug === 'market_research'))
      const run = await legacySend(conversation, 'check BTC', { skill_refs: [{ slug: 'market_research' }] })
      assert.ok(run.events.some(event => event.type === 'message.completed'), JSON.stringify(run.events.map(event => event.type)).slice(0, 300))
      const messages = await legacy('GET', `/conversations/${conversation}`)
      const user = messages.body.messages.find(message => message.role === 'user')
      assert.ok(JSON.stringify(user).includes('market_research'), 'skill recorded on the user message')
      return 'skill_refs resolved server-side; prompt injected into the system prompt'
    },
    compare: () => '相同（能力）/不同（形式）：DSH 由用户输入 `/<skill>` 触发、Skill 正文作为会话消息可审计；旧路径由请求参数 `skill_refs` 选择、服务端注入系统提示',
  })

  await scenario('image', '图片附件', {
    async dsh() {
      const session = await newSession()
      await prompt(session, [{ type: 'text', text: 'what is in this picture' }, { type: 'image', mediaType: 'image/png', data: PNG, name: 'dot.png' }])
      const events = await waitTurns(session, 1)
      exact(replies(events).at(-1), 'I see 1 image(s).')
      return `inline image accepted (no fileUploads); reply "${replies(events).at(-1)}"`
    },
    async legacy() {
      const conversation = await newConversation()
      const upload = await legacy('POST', '/attachments?name=dot.png', null, Buffer.from(PNG, 'base64'))
      assert.equal(upload.status, 200, upload.text.slice(0, 200))
      const run = await legacySend(conversation, 'what is in this picture', { attachments: [{ id: upload.body.attachment.id }] })
      exact(legacyReply(run.events), 'I see 1 image(s).')
      return `upload + reference; reply "${legacyReply(run.events)}"`
    },
    compare: row => row.dsh.status === 'pass' ? '相同：图片到达模型。DSH 走内联图片（不经过被拒绝的 fileUploads）；旧路径先上传再引用' : 'DSH 缺失：见备注',
  })

  await scenario('tool', '工具调用（经 legacy-api 用 Host token 读 FastAPI）', {
    async dsh() {
      const session = await newSession()
      await prompt(session, 'snapshot please [[tool:market_snapshot {"instruments":[]}]]')
      const events = await waitTurns(session, 1)
      const call = events.find(event => event.type === 'tool/call')
      const result = events.find(event => event.type === 'tool/result')
      assert.equal(call?.data?.name, 'market_snapshot', JSON.stringify(events.map(event => event.type)))
      assert.ok(result && !result.data.message?.isError, `tool result: ${JSON.stringify(result?.data).slice(0, 300)}`)
      if (mock) assert.match(replies(events).at(-1), /^Tool market_snapshot returned: /)
      return 'model tool call → legacy-api provider → FastAPI /market/snapshot with the user\'s Host token → result back to the model'
    },
    async legacy() {
      const conversation = await newConversation()
      const run = await legacySend(conversation, 'market snapshot for BTC')
      const tools = run.events.filter(event => event.type === 'tool.completed').map(event => event.data.tool ?? event.data.name)
      assert.ok(run.events.some(event => event.type === 'message.completed'))
      return `server-side planner ran tools [${tools.join(', ')}] before the model call`
    },
    compare: () => '不同：DSH 由模型发起工具调用（tool-use 循环）；旧路径由服务端关键词规划器先运行工具，模型只生成文本',
  })

  await scenario('approval', '工具审批', {
    async dsh() {
      return { status: 'missing', note: '公开 profile 中没有任何会请求审批的工具（bash/jobs/hooks 已禁用，PureGamma 工具都是只读或由 API 自行授权）；审批机制（$events waterfall `approval/request`）存在但无从触发' }
    },
    async legacy() {
      if (!legacyApproval) return { status: 'missing', note: 'STATEFUL_TOOLS 为空，审批不会触发' }
      const conversation = await newConversation()
      let decided
      const run = await legacySend(conversation, 'create a BTC strategy draft', {}, async event => {
        if (event.type === 'approval.required') decided = await legacy('POST', `/tool-calls/${event.data.toolCallId}/approval`, { decision: 'approved' })
      })
      assert.ok(decided, `approval.required not emitted: ${JSON.stringify(run.events.map(event => event.type))}`)
      assert.equal(decided.status, 200)
      return { status: 'pass', note: '仅在测试包装器把 create_strategy_draft 标记为有状态工具后：approval.required → 批准 → tool.completed。出厂配置下 STATEFUL_TOOLS 为空，审批同样不会触发' }
    },
    compare: () => 'DSH 缺失：公开 profile 无需审批的工具；旧路径的审批在出厂配置下同样不可达（STATEFUL_TOOLS 为空），只有测试包装器能触发',
  })
} finally {
  const audit = existsSync(config.audit) ? readFileSync(config.audit, 'utf8').trim().split('\n').length : 0
  const report = {
    at: new Date().toISOString(), database: pgContainer ? 'postgres:17 (docker, throwaway)' : 'sqlite', model: MODEL === 'mock' ? 'local deterministic mock (127.0.0.1)' : 'real model endpoint (DEEPSEEK_BASE_URL)',
    dsh: '@deepseek-ai/dsh 0.1.7-rc.1 via session broker', legacyApprovalWrapper: legacyApproval,
    modelRequests: mockRequests().length, auditLines: audit, results,
  }
  writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2))
  const cell = side => `${side.status}${side.note ? `：${side.note.replace(/\|/g, '/')}` : ''}`
  writeFileSync(path.join(out, 'report.md'), [
    `模型：${report.model}；旧路径数据库：${report.database}；${report.dsh}；模型请求 ${report.modelRequests} 次；审计 ${audit} 行`, '',
    '| 场景 | DSH | 旧 Web 路径 | 对照 |', '| --- | --- | --- | --- |',
    ...results.map(row => `| ${row.title} | ${cell(row.dsh)} | ${cell(row.legacy)} | ${row.comparison} |`),
  ].join('\n'))
  await cleanup()
}
const failed = results.flatMap(row => [row.dsh, row.legacy]).filter(side => side.status === 'fail').length
console.log(`# scenarios ${results.length}, failed sides ${failed}; report: ${out}/report.md`)
process.exit(failed ? 1 : 0)
