#!/usr/bin/env node
// Entry point of a `docker` launcher Host container (plain Node, no build).
//
//   node container-entry.mjs <listenPort> <dsh bin.js> <dsh args...>
//
// DSH Web refuses to bind anything but loopback, and a container's loopback
// is unreachable from the broker. This starts DSH on the container's
// loopback, then forwards <listenPort> on the container interface (published
// by the launcher on the host's 127.0.0.1 only) to it. DSH's own launch-token
// and cookie auth still guard every request. The ready line is echoed only
// once the forwarder listens, so the broker never connects too early.
import { spawn } from 'node:child_process'
import net from 'node:net'
import process from 'node:process'

const [listenPort, dshBin, ...dshArgs] = process.argv.slice(2)
const READY = /^dsh web: http:\/\/127\.0\.0\.1:(\d+)\/\?token=[A-Za-z0-9_-]+/m
const child = spawn(process.execPath, [dshBin, ...dshArgs], { stdio: ['ignore', 'pipe', 'inherit'] })
let server
let buffer = ''
child.stdout.on('data', chunk => {
  if (server) return void process.stdout.write(chunk)
  buffer += String(chunk)
  const match = READY.exec(buffer)
  if (!match) {
    if (buffer.length > 65536) buffer = buffer.slice(-65536)
    return
  }
  const target = Number(match[1])
  server = net.createServer(client => {
    const upstream = net.connect(target, '127.0.0.1')
    const done = () => { client.destroy(); upstream.destroy() }
    for (const side of [client, upstream]) { side.on('error', done); side.on('end', done); side.on('close', done) }
    client.pipe(upstream)
    upstream.pipe(client)
  })
  server.listen(Number(listenPort), '0.0.0.0', () => process.stdout.write(buffer))
})
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    server?.close()
    child.kill('SIGTERM')
    setTimeout(() => child.kill('SIGKILL'), 4000).unref()
  })
}
