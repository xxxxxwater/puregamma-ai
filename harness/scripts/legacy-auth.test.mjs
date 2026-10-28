import assert from 'node:assert/strict'
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { createBearerSource } from '../plugins/legacy-auth/src/index.ts'

// Per-user Hosts read a broker-rotated token file. These pin that a file source
// never falls back to the shared env token and refuses unsafe files.

const dir = mkdtempSync(path.join(tmpdir(), 'pg-legacy-auth-'))
test.after(() => rmSync(dir, { recursive: true, force: true }))
const write = (name, value, mode = 0o600) => {
  const file = path.join(dir, name)
  writeFileSync(file, value)
  chmodSync(file, mode)
  return file
}

test('without a file the env token is used (single-operator Host)', () => {
  process.env.PG_TEST_SHARED = 'shared.token'
  assert.equal(createBearerSource({ authTokenEnv: 'PG_TEST_SHARED' })(), 'shared.token')
})

test('a configured file is the only source: missing file yields no bearer, never the env token', () => {
  process.env.PUREGAMMA_LEGACY_API_TOKEN = 'shared.token'
  const bearer = createBearerSource({ authTokenFile: path.join(dir, 'absent'), authTokenEnv: 'PUREGAMMA_LEGACY_API_TOKEN' })
  assert.equal(bearer(), undefined)
  assert.match(bearer.description, /authTokenFile/)
  delete process.env.PUREGAMMA_LEGACY_API_TOKEN
})

test('the file is re-read after the cache window so the broker can rotate without a restart', () => {
  const file = write('rotating', 'user-a.v1\n')
  let clock = 0
  const bearer = createBearerSource({ authTokenFile: file, authTokenCacheMs: 1000 }, () => clock)
  assert.equal(bearer(), 'user-a.v1')
  write('rotating', 'user-a.v2')
  clock = 500
  assert.equal(bearer(), 'user-a.v1', 'served from cache inside the window')
  clock = 1000
  assert.equal(bearer(), 'user-a.v2')
})

test('group/world-readable, empty or header-smuggling files are refused', { skip: process.platform === 'win32' }, () => {
  assert.equal(createBearerSource({ authTokenFile: write('loose', 'tok.en', 0o644) })(), undefined)
  assert.equal(createBearerSource({ authTokenFile: write('empty', '  \n') })(), undefined)
  assert.equal(createBearerSource({ authTokenFile: write('smuggle', 'tok\r\nX-Evil: 1') })(), undefined)
  assert.equal(createBearerSource({ authTokenFile: dir })(), undefined, 'a directory is not a token file')
})
