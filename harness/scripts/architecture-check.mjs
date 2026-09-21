import { promises as fs } from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = path.resolve(process.cwd())
const repoRoot = path.resolve(root, '..')
const pluginsRoot = path.join(root, 'plugins')
const profilePath = path.join(root, 'profile', 'package.json')
const legacyRoutersRoot = path.join(repoRoot, 'apps', 'api', 'routers')
const legacySurfaceMapPath = path.join(pluginsRoot, 'legacy-surface-map.ts')
const legacyWebRoot = path.join(repoRoot, 'apps', 'web', 'app')
const legacyWebSurfaceMapPath = path.join(pluginsRoot, 'legacy-web-surface-map.ts')
const mainIntegrationMapPath = path.join(pluginsRoot, 'main-integration-surface-map.ts')

const errors = []

async function walk(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    if (entry.name === 'lib' || entry.name === 'node_modules') continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) files.push(...await walk(full))
    else files.push(full)
  }
  return files
}

const sourceFiles = (await walk(pluginsRoot)).filter(file => /\.(?:ts|tsx|js|mjs)$/.test(file))
const forbiddenImportPatterns = [
  /(?:from\s+|import\s*\()['"](?:\.\.\/)+apps\//,
  /(?:from\s+|import\s*\()['"](?:\.\.\/)+packages\//,
  /(?:from\s+|import\s*\()['"](?:\.\.\/)+services\//,
  /(?:from\s+|import\s*\()['"](?:apps|packages|services)\//,
]

for (const file of sourceFiles) {
  const content = await fs.readFile(file, 'utf8')
  for (const pattern of forbiddenImportPatterns) {
    if (pattern.test(content)) {
      errors.push(`${path.relative(root, file)} imports legacy application code directly`)
      break
    }
  }
  if (/new\s+Context\s*\(/.test(content)) {
    errors.push(`${path.relative(root, file)} creates a second Cordis Context; Harness must own the runtime root`)
  }
}

const packageFiles = (await walk(pluginsRoot)).filter(file => path.basename(file) === 'package.json')
for (const file of packageFiles) {
  const pkg = JSON.parse(await fs.readFile(file, 'utf8'))
  if (typeof pkg.name !== 'string' || !pkg.name.startsWith('@puregamma/dsh-')) {
    errors.push(`${path.relative(root, file)} must use the @puregamma/dsh-* plugin namespace`)
  }
  for (const field of ['dependencies', 'peerDependencies', 'optionalDependencies']) {
    for (const [name, version] of Object.entries(pkg[field] ?? {})) {
      if (typeof version === 'string' && /^(?:file:|link:).*(?:apps|packages|services)\//.test(version)) {
        errors.push(`${pkg.name} ${field}.${name} links directly to legacy application code`)
      }
    }
  }
}

const profile = JSON.parse(await fs.readFile(profilePath, 'utf8'))
const expectedBundles = ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app']
if (profile.dsh?.bundle) errors.push('PureGamma product profile must not declare dsh.bundle')
if (!profile.dsh?.profile) {
  errors.push('PureGamma product profile must declare dsh.profile')
} else {
  if (JSON.stringify(profile.dsh.profile.bundles) !== JSON.stringify(expectedBundles)) {
    errors.push(`PureGamma profile must compose the pinned Harness web bundles ${JSON.stringify(expectedBundles)}`)
  }
  if (profile.dsh.profile.patchReload !== 'live') errors.push('PureGamma web profile must use live patch reload')
}
for (const name of Object.keys(profile.dependencies ?? {})) {
  if (!name.startsWith('@puregamma/dsh-')) errors.push(`profile dependency ${name} is not a PureGamma Harness plugin`)
}

// Both ledgers are authoritative. The additive main-only ledger adds explicit
// ownership but does not claim that the associated plugin passes parity.
const mainIntegrationMap = await fs.readFile(mainIntegrationMapPath, 'utf8')
const migrationMap = (await fs.readFile(legacySurfaceMapPath, 'utf8')) + '\n' + mainIntegrationMap
const routerEntries = await fs.readdir(legacyRoutersRoot, { withFileTypes: true })
const routerFiles = routerEntries
  .filter(entry => entry.isFile() && entry.name.endsWith('.py') && entry.name !== '__init__.py')
  .map(entry => entry.name)
  .sort()
for (const router of routerFiles) {
  const surface = `apps/api/routers/${router}`
  if (!migrationMap.includes(`surface: '${surface}'`)) errors.push(`${surface} has no PureGamma Harness plugin owner in migration ledgers`)
}

// Frontend anti-omission gate: every user-addressable legacy Next.js page gets
// an explicit owner and Harness-native destination before the monolith can be
// deleted. Redirect-only pages are included until deletion so old URLs remain
// intentional rather than accidental compatibility behavior.
const webMigrationMap = (await fs.readFile(legacyWebSurfaceMapPath, 'utf8')) + '\n' + mainIntegrationMap
const webPageFiles = (await walk(legacyWebRoot))
  .filter(file => path.basename(file) === 'page.tsx')
  .map(file => path.relative(repoRoot, file).split(path.sep).join('/'))
  .sort()
for (const surface of webPageFiles) {
  if (!webMigrationMap.includes(`surface: '${surface}'`)) errors.push(`${surface} has no Harness plugin owner in migration ledgers`)
}

if (errors.length > 0) {
  console.error('PureGamma Harness architecture check failed:')
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}

console.log(`PureGamma Harness architecture check passed (${sourceFiles.length} source files, ${packageFiles.length} plugin packages, ${routerFiles.length} legacy routers mapped, ${webPageFiles.length} legacy web pages mapped; standalone profile enforced).`)
