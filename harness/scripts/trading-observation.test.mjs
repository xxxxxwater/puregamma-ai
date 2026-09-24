import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = file => readFile(path.join(root, file), 'utf8')

test('observation is a read-only Cordis service, separate from execution and portfolio', async () => {
  const [source, execution, portfolio] = await Promise.all([
    read('plugins/trading-observation/src/index.ts'), read('plugins/trading/src/index.ts'), read('plugins/portfolio/src/index.ts'),
  ])
  assert.match(source, /extends Service/)
  assert.match(source, /super\(ctx, 'pgTradingObservation'\)/)
  assert.match(execution, /super\(ctx, 'pgTrading'\)/)
  assert.match(portfolio, /super\(ctx, 'pgPortfolio'\)/)
  assert.match(source, /abstract positions\(/)
  assert.match(source, /abstract orders\(/)
  assert.match(source, /abstract orderByClientOrderId\(/)
  assert.match(source, /abstract safety\(/)
  assert.doesNotMatch(source, /\b(?:abstract|async)\s+(?:submit|cancel|placeOrder|flatten|approve|reserve|reload|enableLive)\s*\(/)
  assert.match(source, /state: 'unavailable'/)
  assert.match(source, /ownership: 'strategy' \| 'manual' \| 'external' \| 'unknown'/)
})

test('no browser remote or default profile installation until user identity and account authorizations are proven', async () => {
  const [profile, manifest, gateway, contract] = await Promise.all([
    read('profile/cordis.patch.yml'), read('profile/package.json').then(JSON.parse),
    read('packages/client-gateway/src/index.ts'), read('plugins/trading-observation/src/index.ts'),
  ])
  assert.doesNotMatch(profile, /@puregamma\/dsh-trading-observation/)
  assert.equal(manifest.dependencies['@puregamma/dsh-trading-observation'], undefined)
  assert.doesNotMatch(gateway, /pgTradingObservation|@Remote\(['"](?:positions|orders|tradingSafety)['"]\)/)
  assert.match(contract, /authenticate each requesting user/)
  assert.match(contract, /No session principal => unavailable\/deny/)
  assert.match(contract, /NEVER \[\] or healthy/)
})
