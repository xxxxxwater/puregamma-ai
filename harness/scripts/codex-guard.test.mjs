import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { promises as fs } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'

// docs/architecture/AGENT_WORKSPACE_UPGRADE_20261028.md §9: ChatGPT-login
// Codex is not permitted for a hosted multi-user service, and CLI credentials
// (~/.codex/auth.json) are for the owner's own machine only. This guard keeps
// both out of the product: no profile row mounts a Codex/ChatGPT-login
// provider, and no repository code reads Codex CLI credentials.

const harnessRoot = process.cwd()
const repoRoot = path.resolve(harnessRoot, '..')
const self = path.relative(repoRoot, new URL(import.meta.url).pathname)

const PROVIDER_NAME = /codex|chatgpt|openai-(?:login|oauth|account)/i
const CREDENTIAL_READ = [
  /(?:^|['"`/\\])\.codex(?:['"`/\\]|$)/m, // a `.codex` path segment
  /\bCODEX_HOME\b/,
  /codex[^\n]{0,60}auth\.json/i,
  /\bcodex\s+login\b/i,
]

test('no profile row mounts a Codex or ChatGPT-login provider', async () => {
  for (const file of ['cordis.patch.yml', 'multi-tenant.patch.yml']) {
    const text = await fs.readFile(path.join(harnessRoot, 'profile', file), 'utf8')
    for (const match of text.matchAll(/^\s*-?\s*name:\s*['"]?([^'"\s]+)/gm)) {
      assert.doesNotMatch(match[1], PROVIDER_NAME, `${file} mounts ${match[1]}`)
    }
  }
  const manifest = JSON.parse(await fs.readFile(path.join(harnessRoot, 'profile', 'package.json'), 'utf8'))
  for (const name of Object.keys(manifest.dependencies ?? {})) assert.doesNotMatch(name, PROVIDER_NAME)
})

test('no repository code reads Codex CLI credentials', async () => {
  let files
  try {
    files = execFileSync('git', ['ls-files', '-z'], { cwd: repoRoot, encoding: 'utf8' }).split('\0').filter(Boolean)
  } catch {
    return // not a git checkout (source tarball); CI always is one
  }
  const code = files.filter(file => !file.startsWith('vendor/') && file !== self && /\.(?:[cm]?[jt]sx?|py|sh|ya?ml|toml|json)$/.test(file))
  const offenders = []
  for (const file of code) {
    const text = await fs.readFile(path.join(repoRoot, file), 'utf8').catch(() => '')
    if (CREDENTIAL_READ.some(pattern => pattern.test(text))) offenders.push(file)
  }
  assert.deepEqual(offenders, [])
})
