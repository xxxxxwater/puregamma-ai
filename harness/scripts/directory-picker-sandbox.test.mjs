import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { createSandboxCapability } from '../plugins/directory-picker-sandbox/src/index.ts'

// The sandbox picker replaces upstream's Host-wide browse backend. These pin
// its containment: only the root's subtree is listable, `..`/absolute/symlink
// escapes are refused or hidden, creation is refused, no root fails closed.

const outer = realpathSync(mkdtempSync(path.join(tmpdir(), 'pg-picker-')))
const root = path.join(outer, 'user-a', 'workspace')
const other = path.join(outer, 'user-b', 'workspace')
mkdirSync(path.join(root, 'research', 'deep'), { recursive: true })
mkdirSync(path.join(root, '.hidden'), { recursive: true })
mkdirSync(path.join(other, 'secret-plans'), { recursive: true })
writeFileSync(path.join(root, 'notes.txt'), 'x')
symlinkSync(other, path.join(root, 'escape-to-b'))
symlinkSync('/', path.join(root, 'escape-to-root'))
symlinkSync(path.join(root, 'research'), path.join(root, 'inside-link'))
symlinkSync(path.join(outer, 'missing'), path.join(root, 'broken'))
// A sibling whose name shares the root's prefix must not count as inside.
mkdirSync(`${root}-evil`, { recursive: true })
test.after(() => rmSync(outer, { recursive: true, force: true }))

const picker = createSandboxCapability({ root, maxEntries: 100, showHidden: false })
const codeOf = async promise => promise.then(() => 'ok', error => error.code)

test('listing defaults to the root and offers only directories inside it', async () => {
  const listing = await picker.list()
  assert.equal(listing.path, root)
  assert.equal(listing.home, root)
  assert.deepEqual(listing.entries.map(entry => entry.name), ['inside-link', 'research'])
  assert.equal(listing.entries.find(entry => entry.name === 'inside-link').path, path.join(root, 'research'))
  assert.deepEqual(listing.crumbs.map(crumb => crumb.path), [root])
  const nested = await picker.list(path.join(root, 'research', 'deep'))
  assert.deepEqual(nested.crumbs.map(crumb => crumb.path), [root, path.join(root, 'research'), path.join(root, 'research', 'deep')])
})

test('paths outside the root are refused however they are spelled', async () => {
  for (const target of [
    outer, other, path.join(other, 'secret-plans'), '/', '/etc',
    path.join(root, '..'), path.join(root, '..', '..', 'user-b', 'workspace'),
    path.join(root, 'escape-to-b'), path.join(root, 'escape-to-root'), `${root}-evil`,
    'research', '', `${root}\0`,
  ]) {
    assert.equal(await codeOf(picker.list(target)), 'directory-unreadable', target)
  }
  assert.equal(await codeOf(picker.list(path.join(root, 'notes.txt'))), 'directory-unreadable')
})

test('directory creation is refused and pick answers the root', async () => {
  assert.equal(await codeOf(picker.createDirectory(root, 'new')), 'directory-create-failed')
  assert.equal(await codeOf(picker.createDirectory('/tmp', 'x')), 'directory-create-failed')
  assert.equal(await picker.pick(), root)
})

test('no configured root fails closed', async () => {
  for (const rootless of [undefined, '', 'relative/root', path.join(outer, 'does-not-exist')]) {
    const closed = createSandboxCapability({ root: rootless, maxEntries: 10, showHidden: false })
    assert.equal(await codeOf(closed.list()), 'directory-unreadable')
    assert.equal(await codeOf(closed.list('/')), 'directory-unreadable')
  }
})

test('hidden directories stay hidden unless enabled and listings are bounded', async () => {
  const shown = await createSandboxCapability({ root, maxEntries: 100, showHidden: true }).list()
  assert.ok(shown.entries.some(entry => entry.name === '.hidden' && entry.hidden))
  const bounded = await createSandboxCapability({ root, maxEntries: 1, showHidden: true }).list()
  assert.equal(bounded.entries.length, 1)
  assert.equal(bounded.truncated, true)
})
