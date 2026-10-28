#!/usr/bin/env node
import process from 'node:process'
import { loadConfig, validateConfig } from './config.ts'
import { createBroker } from './server.ts'

const config = loadConfig()
const errors = validateConfig(config)
if (errors.length) {
  for (const error of errors) console.error(`[dsh-broker] ${error}`)
  process.exit(2)
}
const broker = createBroker(config)
broker.server.listen(config.listenPort, config.listenHost, () => {
  const address = broker.server.address()
  const port = typeof address === 'object' && address ? address.port : config.listenPort
  console.log(`[dsh-broker] listening on ${config.listenHost}:${port} for ${config.publicOrigin} (max ${config.maxHosts} hosts)`)
})
for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.once(signal, () => void broker.close().finally(() => process.exit(0)))
}
