import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { validateRetirement } from './retirement-gate.mjs'

/**
 * A migration owner is NOT parity evidence. Keep historical rows indefinitely:
 * removing an old route requires a reviewed per-route certificate, even when
 * the new Harness profile builds. This check is intentionally read-only.
 * Rules: scripts/retirement-gate.mjs (unit-tested by retirement-check.test.mjs).
 */
const harness = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repo = path.resolve(harness, '..')
const read = relative => readFile(path.join(harness, relative), 'utf8')
const [webMap, apiMap, certificateText] = await Promise.all([
  read('plugins/legacy-web-surface-map.ts'),
  read('plugins/legacy-surface-map.ts'),
  read('retirement-evidence.json'),
])
const result = validateRetirement({ webMap, apiMap, certificate: JSON.parse(certificateText), exists: surface => existsSync(path.join(repo, surface)) })
if (result.errors.length) {
  console.error('PureGamma legacy retirement gate FAILED:')
  for (const error of result.errors) console.error(`- ${error}`)
  process.exitCode = 1
} else {
  const progress = result.candidates.map(item => `${item.surface} ${item.met}/${item.total} gates met`).join('; ')
  console.log(`PureGamma legacy retirement gate passed: ${result.web} web + ${result.api} router historical owners; ${result.present} files retained, ${result.retired} certified retired${progress ? `; candidates (not retired): ${progress}` : ''}. This does NOT prove functional parity or authorize cutover.`)
}
