// Stand-in for `dsh <profile> --port 0 --no-open` with the same outward
// contract the broker relies on: the ready line, the `/?token=` exchange for a
// `dsh-auth-*` cookie, the loopback Host/Origin fence, and a Session store
// under DSH_HOME. Used by session-broker.test.mjs only.
import { createHash, randomBytes } from 'node:crypto'
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import process from 'node:process'

const home = process.env.DSH_HOME
const sessions = path.join(home, 'sessions')
mkdirSync(sessions, { recursive: true })
const token = randomBytes(16).toString('base64url')
const cookie = `dsh-auth-test=${randomBytes(16).toString('base64url')}`
let port = 0

const fenced = req => {
  if (req.headers.host !== `127.0.0.1:${port}`) return 403
  if (req.headers.origin !== undefined && req.headers.origin !== `http://127.0.0.1:${port}`) return 403
  if (!(req.headers.cookie ?? '').split(';').map(s => s.trim()).includes(cookie)) return 401
  return 0
}
const json = (res, status, body) => { res.writeHead(status, { 'content-type': 'application/json', 'set-cookie': 'leak=1' }); res.end(JSON.stringify(body)) }

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x')
  if (url.pathname === '/' && url.searchParams.get('token') === token) {
    res.writeHead(303, { location: './', 'set-cookie': `${cookie}; Path=/; HttpOnly; SameSite=Strict` })
    return res.end()
  }
  const rejected = fenced(req)
  if (rejected) return json(res, rejected, { error: 'fence' })
  let body = ''
  req.on('data', chunk => { body += chunk })
  req.on('end', () => {
    if (url.pathname === '/api/session/create') {
      const { title } = JSON.parse(body || '{}')
      writeFileSync(path.join(sessions, `${createHash('sha256').update(title).digest('hex').slice(0, 8)}.json`), JSON.stringify({ title }))
      return json(res, 200, { ok: true })
    }
    if (url.pathname === '/api/session/list') {
      return json(res, 200, { sessions: readdirSync(sessions).map(f => JSON.parse(readFileSync(path.join(sessions, f), 'utf8')).title) })
    }
    if (url.pathname === '/api/debug') {
      return json(res, 200, {
        home, cwd: process.cwd(), query: url.search, cookie: req.headers.cookie, authorization: req.headers.authorization ?? null,
        tokenFile: process.env.PUREGAMMA_LEGACY_API_TOKEN_FILE, sharedToken: process.env.PUREGAMMA_LEGACY_API_TOKEN ?? null,
        brokerSecret: process.env.PUREGAMMA_DSH_BROKER_SECRET ?? null, workspaceRoot: process.env.PUREGAMMA_DSH_WORKSPACE_ROOT,
      })
    }
    json(res, 404, { error: 'not found' })
  })
})
server.on('upgrade', (req, socket) => {
  const rejected = req.url !== '/api/remote.mux' ? 404 : fenced(req)
  if (rejected) return socket.end(`HTTP/1.1 ${rejected} Rejected\r\nConnection: close\r\n\r\n`)
  const accept = createHash('sha1').update(`${req.headers['sec-websocket-key']}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`).digest('base64')
  socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`)
  socket.write(`hello from ${home}\n`)
  socket.on('error', () => {})
})
server.listen(0, '127.0.0.1', () => {
  port = server.address().port
  console.log(`dsh web: http://127.0.0.1:${port}/?token=${token}`)
  console.log('dsh web: opening the default browser; pass --no-open to disable')
})
process.on('SIGTERM', () => server.close(() => process.exit(0)))
