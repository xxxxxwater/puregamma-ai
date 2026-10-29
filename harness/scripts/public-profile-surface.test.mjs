import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, promises as fs, readFileSync } from 'node:fs'
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
// CI checks out the pinned submodule. A worktree without it (it is 2.2 GB)
// falls back to the npm publication of the same pinned version, which ships
// the same patch layers; the version is asserted so the two cannot drift.
const vendorWebAppDir = path.join(repoRoot, 'vendor', 'deepseek-harness', 'packages', 'bundle', 'web-app')
const npmWebAppDir = path.join(harnessRoot, 'node_modules', '@deepseek-ai', 'dsh-web-app')
const webAppDir = existsSync(path.join(vendorWebAppDir, 'package.json')) ? vendorWebAppDir : npmWebAppDir
if (webAppDir === npmWebAppDir) {
  const pinned = JSON.parse(readFileSync(path.join(harnessRoot, 'package.json'), 'utf8')).devDependencies['@deepseek-ai/dsh-web-app']
  const published = JSON.parse(readFileSync(path.join(npmWebAppDir, 'package.json'), 'utf8')).version
  if (published !== pinned) throw new Error(`npm dsh-web-app ${published} is not the pinned ${pinned}`)
}

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
const overlayRows = topLevelRows(await loadPatch(path.join(harnessRoot, 'profile', 'multi-tenant.patch.yml')))

/** Bundle rows (every patch layer the pinned web-app bundle declares), keyed by id. */
async function bundleRows() {
  const manifest = JSON.parse(await fs.readFile(path.join(webAppDir, 'package.json'), 'utf8'))
  const rows = new Map()
  for (const relative of manifest.dsh?.bundle?.patch ?? []) {
    for (const [id, row] of topLevelRows(await loadPatch(path.join(webAppDir, relative)))) rows.set(id, row)
  }
  return rows
}

/**
 * Layer patch rows by id the way the launcher does: a later row merges into
 * the earlier one, but a row naming a different plugin is skipped (the
 * launcher logs "name mismatch ... skipping"), so a rename never takes effect.
 */
function compose(...layers) {
  const out = new Map()
  for (const layer of layers) {
    for (const [id, row] of layer) {
      const prior = out.get(id)
      if (prior?.name && row.name && row.name !== prior.name) continue
      out.set(id, { ...(prior ?? {}), ...row })
    }
  }
  return out
}

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

test('the single-operator profile keeps the Session sidebar off', () => {
  assert.equal(profileRows.get('ui-sidebar')?.disabled, true, 'ui-sidebar only returns through the broker-applied multi-tenant overlay')
})

test('every Host uses the sandboxed directory picker, never the Host-wide upstream backends', async () => {
  assert.equal(profileRows.get('directory-picker')?.disabled, true, 'the Host-wide upstream picker row stays disabled')
  assert.equal(profileRows.get('directory-picker')?.name, undefined, 'a patch row cannot rename a plugin')
  const picker = profileRows.get('puregamma-directory-picker')
  assert.equal(picker?.name, '@puregamma/dsh-directory-picker-sandbox')
  assert.deepEqual(picker?.config?.root, { __jsExpr: "process.env.PUREGAMMA_DSH_WORKSPACE_ROOT ?? ''" })
  assert.equal(picker?.config?.showHidden, false)
  const effective = compose(await bundleRows(), profileRows, overlayRows)
  const names = [...effective.values()].filter(row => row.disabled !== true).map(row => row.name)
  for (const upstream of ['@deepseek-ai/dsh-host-directory-picker-auto', '@deepseek-ai/dsh-host-directory-picker-browse', '@deepseek-ai/dsh-host-directory-picker-native']) {
    assert.ok(!names.includes(upstream), `${upstream} must not be mounted`)
  }
})

test('the multi-tenant overlay only re-enables the Session list and relaxes nothing else', async () => {
  assert.deepEqual([...overlayRows.keys()].sort(), ['ui-sidebar', 'ui-workspace'])
  for (const row of overlayRows.values()) assert.deepEqual(Object.keys(row).sort(), ['disabled', 'id'])
  const effective = compose(await bundleRows(), profileRows, overlayRows)
  assert.equal(effective.get('ui-sidebar')?.disabled, false)
  assert.equal(effective.get('ui-workspace')?.disabled, false)
  assert.equal(effective.get('ui-workspace')?.name, '@deepseek-ai/dsh-client-ui-workspace')
  for (const id of ['file-upload', 'terminal-controller', 'workspace-files', 'ui-sidebar-terminal', 'ui-sidebar-files', 'ui-plugin-manager', 'preset-ptc', 'preset-minimal', 'preset-cordis']) {
    assert.equal(effective.get(id)?.disabled, true, `${id} must stay disabled with the multi-tenant overlay`)
  }
  assert.equal(effective.get('directory-picker')?.disabled, true)
  assert.equal(effective.get('puregamma-directory-picker')?.name, '@puregamma/dsh-directory-picker-sandbox')
})

test('every legacy-api provider can take a per-user token file and never needs the shared token in a broker Host', () => {
  const providers = [...profileRows.values()].filter(row => /-legacy-api'?$/.test(row.name ?? ''))
  assert.ok(providers.length >= 14)
  for (const row of providers) {
    assert.deepEqual(row.config?.authTokenFile, { __jsExpr: 'process.env.PUREGAMMA_LEGACY_API_TOKEN_FILE' }, `${row.id} must read PUREGAMMA_LEGACY_API_TOKEN_FILE`)
  }
})

test('profile rows that name an existing id never rename its plugin (the launcher would skip them)', async () => {
  const bundle = await bundleRows()
  for (const [id, row] of [...profileRows, ...overlayRows]) {
    const upstream = bundle.get(id)
    if (upstream?.name && row.name) assert.equal(row.name, upstream.name, `${id} renames ${upstream.name}`)
  }
})

test('the Session controller gets a fileUploads provider that admits nothing, while upstream uploads stay off', async () => {
  assert.equal(profileRows.get('file-upload')?.disabled, true)
  assert.equal(profileRows.get('puregamma-file-uploads-refused')?.name, '@puregamma/dsh-file-uploads-refused')
  const source = await fs.readFile(path.join(harnessRoot, 'plugins', 'file-uploads-refused', 'src', 'index.ts'), 'utf8')
  assert.doesNotMatch(source, /connection\.fetch|@Remote|TypertRemoteService|admitEncodedFile/, 'no upload route, Remote or admission')
  const { default: Refused } = await import('../plugins/file-uploads-refused/src/index.ts')
  const refused = Object.create(Refused.prototype)
  assert.equal(refused.resolve({}, 'receipt-1'), undefined)
  assert.throws(() => refused.bindPrompt({}, ['receipt-1'], 'r'), /disabled/)
  const binding = refused.bindPrompt({}, [], 'r')
  binding.commit()
  binding[Symbol.dispose]()
})

test('the browser gets a fileUpload service that refuses every upload without touching the network', async () => {
  // Upstream's client Session controller injects `fileUpload`; without a
  // provider every chat/session client plugin stays pending in the browser.
  const manifest = JSON.parse(await fs.readFile(path.join(harnessRoot, 'plugins', 'file-uploads-refused', 'package.json'), 'utf8'))
  assert.equal(manifest.dsh?.client?.platform, 'web')
  assert.equal(manifest.exports['./client'].default, './lib/client.js')
  const source = await fs.readFile(path.join(harnessRoot, 'plugins', 'file-uploads-refused', 'src', 'client', 'index.ts'), 'utf8')
  assert.doesNotMatch(source, /fetch\(|XMLHttpRequest|Worker\(|remote\.fileUploads/, 'no transport of any kind')
  const { RefusedFileUpload, UPLOAD_DISABLED_CODE } = await import('../plugins/file-uploads-refused/src/client/index.ts')
  const service = Object.create(RefusedFileUpload.prototype)
  const result = await service.upload('session-1', new Uint8Array([1, 2, 3]), 'a.png')
  assert.equal(result.ok, false)
  assert.equal(result.error.code, UPLOAD_DISABLED_CODE)
  await assert.rejects(service.post({ path: 'x', body: new Uint8Array() }), /disabled/)
})

test('the research/backtest resource views ship off, and their overlay flips only that row', async () => {
  const row = profileRows.get('puregamma-ui-research-resources')
  assert.equal(row?.name, '@puregamma/dsh-ui-research-resources')
  assert.equal(row?.disabled, true, 'new resource views are off unless resource-views.patch.yml is applied')
  const viewRows = topLevelRows(await loadPatch(path.join(harnessRoot, 'profile', 'resource-views.patch.yml')))
  assert.deepEqual([...viewRows.keys()], ['puregamma-ui-research-resources'])
  assert.deepEqual(viewRows.get('puregamma-ui-research-resources'), { id: 'puregamma-ui-research-resources', disabled: false })
  for (const overlays of [[viewRows], [overlayRows, viewRows]]) {
    const effective = compose(await bundleRows(), profileRows, ...overlays)
    assert.equal(effective.get('puregamma-ui-research-resources')?.disabled, false)
    for (const id of ['file-upload', 'terminal-controller', 'workspace-files', 'ui-sidebar-terminal', 'ui-sidebar-files', 'ui-plugin-manager', 'preset-ptc', 'preset-minimal', 'preset-cordis', 'directory-picker']) {
      assert.equal(effective.get(id)?.disabled, true, `${id} must stay disabled with the resource-views overlay`)
    }
  }
  // Browser-only plugin: it injects only resource/sidebar/locale services and
  // the PureGamma Remote assembly; nothing that reaches files, shells or uploads.
  const manifest = JSON.parse(await fs.readFile(path.join(harnessRoot, 'plugins', 'ui-research-resources', 'package.json'), 'utf8'))
  assert.deepEqual(manifest.dsh.client.inject, ['@puregamma/dsh-client-remotes', '@deepseek-ai/dsh-client-resources', '@deepseek-ai/dsh-client-ui-sidebar-right', '@deepseek-ai/dsh-client-locale', '@deepseek-ai/dsh-client-ui-renderer'])
  const host = await fs.readFile(path.join(harnessRoot, 'plugins', 'ui-research-resources', 'src', 'index.ts'), 'utf8')
  assert.match(host, /export function apply\(\): void \{\}/, 'the Host half registers nothing')
})
