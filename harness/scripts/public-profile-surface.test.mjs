import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { promises as fs } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import * as yaml from 'js-yaml'

// The public PureGamma profile is composed on top of the pinned
// `@deepseek-ai/dsh-web-app` bundle. Checking only the profile file misses
// rows the bundle inserts (agent presets in particular), so this test resolves
// the bundle's own patch list and applies the profile's row overrides by id.

const harnessRoot = process.cwd()
const repoRoot = path.resolve(harnessRoot, '..')
const webAppDir = path.join(repoRoot, 'vendor', 'deepseek-harness', 'packages', 'bundle', 'web-app')

const JsExpr = new yaml.Type('tag:yaml.org,2002:js', {
  kind: 'scalar',
  resolve: data => typeof data === 'string',
  construct: data => ({ __jsExpr: data }),
})
const schema = yaml.JSON_SCHEMA.extend(JsExpr)
const loadPatch = async file => yaml.load(await fs.readFile(file, 'utf8'), { schema }) ?? []

/** Tool and runtime rows a multi-user website must never offer a Web user. */
const FORBIDDEN = [
  /^@deepseek-ai\/dsh-tool-bash/,
  /^@deepseek-ai\/dsh-tool-pwsh/,
  /^@deepseek-ai\/dsh-tool-fs/,
  /^@deepseek-ai\/dsh-tool-jobs/,
  /^@deepseek-ai\/dsh-terminal/,
  /^@deepseek-ai\/dsh-tool-subagent/,
  /^@deepseek-ai\/dsh-tool-workflow/,
  /^@deepseek-ai\/dsh-.*ralph/,
  /^@deepseek-ai\/dsh-plugin-manager/,
]

function plugins(rows, into = []) {
  for (const row of rows ?? []) {
    if (!row || typeof row !== 'object') continue
    if (typeof row.name === 'string' && row.name !== 'cordis:group') into.push(row.name)
    if (Array.isArray(row.config)) plugins(row.config, into)
    if (Array.isArray(row.config?.plugins)) plugins(row.config.plugins, into)
  }
  return into
}

function topLevelRows(patch) {
  const rows = new Map()
  for (const entry of patch) {
    if (!entry || typeof entry !== 'object') continue
    if (Array.isArray(entry.insert)) {
      for (const row of entry.insert) if (row?.id) rows.set(row.id, row)
    } else if (entry.id) {
      rows.set(entry.id, entry)
    }
  }
  return rows
}

async function bundlePresets() {
  const manifest = JSON.parse(await fs.readFile(path.join(webAppDir, 'package.json'), 'utf8'))
  const presets = new Map()
  for (const relative of manifest.dsh?.bundle?.patch ?? []) {
    for (const [id, row] of topLevelRows(await loadPatch(path.join(webAppDir, relative)))) {
      if (row.name === '@deepseek-ai/dsh-agent-preset') presets.set(id, row)
    }
  }
  return presets
}

const profileRows = topLevelRows(await loadPatch(path.join(harnessRoot, 'profile', 'cordis.patch.yml')))

test('every agent preset still enabled in the public profile is free of host shell, filesystem and delegation tools', async () => {
  const presets = await bundlePresets()
  assert.ok(presets.size >= 4, `expected the pinned web-app bundle to declare its presets, found ${[...presets.keys()]}`)
  const enabled = []
  for (const [id, bundleRow] of presets) {
    const override = profileRows.get(id)
    if (override?.disabled === true) continue
    // Cordis replaces a row's config wholesale when the profile names the row.
    const effective = override?.config ? override : bundleRow
    const offending = plugins([effective]).filter(name => FORBIDDEN.some(pattern => pattern.test(name)))
    assert.deepEqual(offending, [], `preset ${id} would expose ${offending.join(', ')} to Web users`)
    enabled.push(id)
  }
  assert.deepEqual(enabled, ['preset-standard'], 'only the hardened standard preset may remain selectable')
})

test('coding-workspace host surfaces stay disabled for the public website', () => {
  for (const id of ['file-upload', 'terminal-controller', 'workspace-files', 'ui-sidebar-terminal', 'ui-sidebar-files', 'ui-plugin-manager']) {
    assert.equal(profileRows.get(id)?.disabled, true, `${id} must be disabled in the public profile`)
  }
})

test('the hardened standard preset reads only the bundled PureGamma skills', () => {
  const standard = profileRows.get('preset-standard')
  const skills = standard?.config?.plugins?.find(row => row.id === 'skill-filesystem')
  assert.equal(skills?.config?.includeDefaultRoots, false)
  assert.equal(skills?.config?.watch, false)
})

test('the PureGamma Remote gateway is mounted by the plugin that ships its browser half', async () => {
  const source = await fs.readFile(path.join(harnessRoot, 'plugins', 'client-remotes', 'src', 'index.ts'), 'utf8')
  assert.match(source, /ctx\.plugin\(PureGammaClientGateway\)/)
  assert.ok(profileRows.has('puregamma-client-remotes'), 'the profile must mount @puregamma/dsh-client-remotes')
})

test('README pins match the gitlinks CI verifies', async () => {
  const readme = await fs.readFile(path.join(harnessRoot, 'README.md'), 'utf8')
  for (const submodule of ['vendor/deepseek-harness', 'vendor/pg-tsy-core-bootstrap']) {
    let line
    try {
      line = execFileSync('git', ['ls-tree', 'HEAD', submodule], { cwd: repoRoot, encoding: 'utf8' }).trim()
    } catch {
      return // not a git checkout (e.g. a source tarball); CI always is one
    }
    const sha = line.split(/\s+/)[2]
    assert.match(sha ?? '', /^[0-9a-f]{40}$/, `cannot read gitlink for ${submodule}`)
    assert.ok(readme.includes(sha), `harness/README.md must name the ${submodule} gitlink ${sha}`)
  }
})
