import { readFile, access } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

/**
 * A migration owner is NOT parity evidence. Keep historical rows indefinitely:
 * removing an old route requires a reviewed per-route certificate, even when
 * the new Harness profile builds. This check is intentionally read-only.
 */
const harness = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repo = path.resolve(harness, '..')
const read = relative => readFile(path.join(harness, relative), 'utf8')
const errors = []
const [webMap, apiMap, certificateText] = await Promise.all([
  read('plugins/legacy-web-surface-map.ts'),
  read('plugins/legacy-surface-map.ts'),
  read('retirement-evidence.json'),
])
const certificate = JSON.parse(certificateText)
if (certificate.schemaVersion !== 1 || !certificate.retired || typeof certificate.retired !== 'object' || Array.isArray(certificate.retired)) {
  throw new Error('retirement-evidence.json must contain schemaVersion=1 and a retired object')
}

function rows(text, prefix) {
  const entries = [...text.matchAll(/\{\s*surface:\s*'([^']+)'\s*,\s*(?:owner|target):\s*'([^']+)'/g)]
    .map(([, surface, owner]) => ({ surface, owner }))
    .filter(({ surface }) => surface.startsWith(prefix))
  const seen = new Set()
  for (const entry of entries) {
    if (seen.has(entry.surface)) errors.push(`duplicate migration owner: ${entry.surface}`)
    seen.add(entry.surface)
  }
  return entries
}

const web = rows(webMap, 'apps/web/app/')
const api = rows(apiMap, 'apps/api/routers/')
// Ledger rows must NOT disappear as pages retire: history is the anti-omission baseline.
if (web.length < 83) errors.push(`web migration ledger shrank below 83 baseline entries: ${web.length}`)
if (api.length < 38) errors.push(`API router migration ledger shrank below 38 baseline entries: ${api.length}`)
const all = [...web, ...api]
const owners = new Map(all.map(row => [row.surface, row.owner]))

for (const [surface, evidence] of Object.entries(certificate.retired)) {
  if (!owners.has(surface)) errors.push(`retirement certificate has no preserved migration owner: ${surface}`)
  if (typeof evidence !== 'object' || evidence === null || Array.isArray(evidence)) {
    errors.push(`retirement certificate must be an object: ${surface}`)
    continue
  }
  if (evidence.owner !== owners.get(surface)) errors.push(`retirement owner mismatch: ${surface}`)
  const required = ['replacementPlugin', 'identityBinding', 'readWritePermissions', 'observableStates', 'bilingualUi', 'lifecycleCleanup', 'streamAndBinaryParity', 'e2eArtifactUrl', 'rollbackProcedure', 'reviewedBy', 'verifiedAt']
  for (const field of required) {
    if (typeof evidence[field] !== 'string' || evidence[field].trim().length < 8) errors.push(`retirement evidence ${surface} missing ${field}`)
  }
  if (!/^[0-9a-f]{40}$/.test(String(evidence.integratedCommit ?? ''))) errors.push(`retirement evidence ${surface} missing exact integrated commit SHA`)
  if (!/^sha256:[0-9a-f]{64}$/.test(String(evidence.imageDigest ?? ''))) errors.push(`retirement evidence ${surface} missing immutable deployment image digest`)
  if (!/^https:\/\//.test(String(evidence.e2eArtifactUrl ?? ''))) errors.push(`retirement evidence ${surface} missing HTTPS E2E artifact URL`)
  if (!Number.isFinite(Date.parse(String(evidence.verifiedAt ?? '')))) errors.push(`retirement evidence ${surface} invalid verification timestamp`)
}

let present = 0
let retired = 0
for (const { surface } of all) {
  try {
    await access(path.join(repo, surface))
    present++
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
    retired++
    if (!Object.hasOwn(certificate.retired, surface)) errors.push(`legacy route deleted without verified retirement certificate: ${surface}`)
  }
}
if (errors.length) {
  console.error('PureGamma legacy retirement gate FAILED:')
  for (const error of errors) console.error(`- ${error}`)
  process.exitCode = 1
} else {
  console.log(`PureGamma legacy retirement gate passed: ${web.length} web + ${api.length} router historical owners; ${present} files retained, ${retired} certified retired. This does NOT prove functional parity or authorize cutover.`)
}
