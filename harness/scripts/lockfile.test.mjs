import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import * as yaml from 'js-yaml'

// The Harness workspace installs from a committed pnpm-lock.yaml with
// --frozen-lockfile. A stale or hand-merged lockfile once resolved
// @deepseek-ai/cordis into two peer variants: two copies of the Cordis class,
// so `ctx.slots`-style augmentations stopped applying (TS2339 in
// plugins/brand) while every version number still looked right. These checks
// pin the shape that matters. Update procedure: docs/architecture/
// upgrade-20261029/harness-repro-visual.md ("升级 DSH 时更新 lockfile").

const root = process.cwd()
const manifest = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8'))
const lockPath = path.join(root, 'pnpm-lock.yaml')
const lock = existsSync(lockPath) ? yaml.load(readFileSync(lockPath, 'utf8')) : undefined
const PINNED_DSH = manifest.devDependencies['@deepseek-ai/dsh-web-app']
const PINNED_CORDIS = manifest.devDependencies['@deepseek-ai/cordis']

/** `@scope/name@1.2.3(peer@x)` → { name, version, id } */
function parseKey(key) {
  const match = /^(@?[^@]+)@([^(]+)(.*)$/.exec(key)
  return match ? { name: match[1], version: match[2], id: key } : undefined
}

/** Every `name → resolved` reference in importers and snapshots. */
function references(name) {
  const out = []
  const visit = (owner, deps) => {
    for (const [dep, value] of Object.entries(deps ?? {})) {
      if (dep !== name) continue
      out.push({ owner, resolved: typeof value === 'string' ? value : value.version })
    }
  }
  for (const [importer, entry] of Object.entries(lock.importers ?? {})) {
    for (const field of ['dependencies', 'devDependencies', 'optionalDependencies']) visit(`importer ${importer}`, entry[field])
  }
  for (const [snapshot, entry] of Object.entries(lock.snapshots ?? {})) {
    for (const field of ['dependencies', 'optionalDependencies']) visit(snapshot, entry[field])
  }
  return out
}

test('the lockfile is committed and written by the pinned pnpm', () => {
  assert.ok(lock, 'harness/pnpm-lock.yaml must exist; CI installs it with --frozen-lockfile')
  assert.equal(manifest.packageManager, 'pnpm@11.7.0', 'regenerate the lockfile when the pinned pnpm changes')
  assert.equal(lock.lockfileVersion, '9.0')
})

test('@deepseek-ai/cordis resolves to exactly one version and one peer variant', () => {
  const packages = Object.keys(lock.packages).map(parseKey).filter(entry => entry?.name === '@deepseek-ai/cordis')
  assert.deepEqual(packages.map(entry => entry.version), [PINNED_CORDIS])
  const snapshots = Object.keys(lock.snapshots).map(parseKey).filter(entry => entry?.name === '@deepseek-ai/cordis')
  assert.equal(snapshots.length, 1, `cordis split into peer variants: ${snapshots.map(entry => entry.id).join(', ')}`)
  const variant = snapshots[0].id.slice('@deepseek-ai/cordis@'.length)
  const stray = references('@deepseek-ai/cordis').filter(reference => reference.resolved !== variant)
  assert.deepEqual(stray, [], 'every consumer must link the one cordis variant')
})

test('every @deepseek-ai/dsh-* package resolves to the pinned DeepSeek Harness version', () => {
  const drift = Object.keys(lock.packages).map(parseKey)
    .filter(entry => entry && /^@deepseek-ai\/dsh(-|$)/.test(entry.name) && entry.version !== PINNED_DSH)
    .map(entry => entry.id)
  assert.deepEqual(drift, [], `DSH packages must all be ${PINNED_DSH}`)
})

test('the importers match the workspace manifests', () => {
  const importers = Object.keys(lock.importers).sort()
  const expected = ['.', 'profile']
  for (const dir of ['packages', 'plugins']) {
    for (const name of readdirSync(path.join(root, dir))) {
      if (existsSync(path.join(root, dir, name, 'package.json'))) expected.push(`${dir}/${name}`)
    }
  }
  assert.deepEqual(importers, expected.sort(), 'a workspace package was added or removed without regenerating the lockfile')
})

test('an installed tree carries one cordis copy (catches a stale local node_modules)', { skip: !existsSync(path.join(root, 'node_modules', '.pnpm')) && 'not installed' }, () => {
  const copies = readdirSync(path.join(root, 'node_modules', '.pnpm')).filter(name => name.startsWith('@deepseek-ai+cordis@'))
  assert.equal(copies.length, 1, `found ${copies.join(', ')}; delete harness node_modules and reinstall with --frozen-lockfile`)
})
