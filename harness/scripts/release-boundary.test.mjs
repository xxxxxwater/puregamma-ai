import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = relative => readFile(path.join(root, relative), 'utf8')

// These are deliberate *negative* release invariants. They do not establish
// that a live adapter is ready, nor substitute for exchange/staging evidence.
test('the mounted profile cannot implicitly activate real trading or runtime reload', async () => {
  const [profile, manifest] = await Promise.all([
    read('profile/cordis.patch.yml'),
    read('profile/package.json').then(JSON.parse),
  ])
  assert.match(profile, /id: puregamma-pg-tsy-runtime\s*\n\s*name: '@puregamma\/dsh-pg-tsy-runtime-http'[\s\S]*?allowStrategyReload: false/)
  assert.doesNotMatch(profile, /name:\s*['"]?@puregamma\/dsh-(?:trading|trading-mandates)(?:-legacy-api|-live|-provider)?['"]?(?:\s|$)/m)
  assert.doesNotMatch(profile, /LIVE_TRADING_(?:ENABLED|DEPLOYMENT_APPROVED)\s*[:=]\s*true/)
  for (const name of Object.keys(manifest.dependencies ?? {})) {
    assert.doesNotMatch(name, /^@puregamma\/dsh-(?:trading|trading-mandates)(?:-legacy-api|-live|-provider)?$/)
  }
})

test('the browser Remote only exposes reviewed account/billing/notification/health commands', async () => {
  const gateway = await read('packages/client-gateway/src/index.ts')
  const exposed = [...gateway.matchAll(/@Remote\(['"]([^'"]+)['"]\)/g)].map(match => match[1]).sort()
  const reviewed = [
    'account', 'billing', 'billingCheckout', 'billingPaymentLinkCheckout', 'billingPortal',
    'billingCancel', 'billingReactivate', 'notifications', 'notificationsUpdateDailyBrief',
    'notificationsRequestImessageVerification', 'notificationsConfirmImessageVerification',
    'notificationsTestImessage', 'notificationsTestEmail', 'quantRuntime',
  ].sort()
  assert.deepEqual(exposed, reviewed)
  assert.doesNotMatch(gateway, /@Remote\(['"](?:submit|placeOrder|flatten|emergencyExit|reloadStrategies)['"]\)/)
})

test('plugin-owned browser surfaces use Host Remote/Resources, never old direct HTTP', async () => {
  const plugins = path.join(root, 'plugins')
  for (const dirent of await readdir(plugins, { withFileTypes: true })) {
    if (!dirent.isDirectory() || !dirent.name.startsWith('ui-')) continue
    const client = path.join(plugins, dirent.name, 'src', 'client')
    let entries
    try { entries = await readdir(client, { withFileTypes: true }) } catch (error) {
      if (error.code === 'ENOENT') continue
      throw error
    }
    for (const entry of entries) {
      if (!entry.isFile() || !/\.(?:tsx?|jsx?)$/.test(entry.name)) continue
      const source = await readFile(path.join(client, entry.name), 'utf8')
      assert.doesNotMatch(source, /\bfetch\s*\(|\bXMLHttpRequest\b|axios\s*\./, `${dirent.name}/${entry.name} bypasses Host Remote`)
      assert.doesNotMatch(source, /from\s*['"][^'"]*(?:apps\/web|apps\/api|packages\/live_trading)[^'"]*['"]/, `${dirent.name}/${entry.name} imports a legacy implementation`)
    }
  }
})
