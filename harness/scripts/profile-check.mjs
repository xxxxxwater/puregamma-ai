import { promises as fs } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import process from 'node:process'
import * as yaml from 'js-yaml'

const root = path.resolve(process.cwd())
const profileDir = path.join(root, 'profile')
const manifestPath = path.join(profileDir, 'package.json')
const patchPath = path.join(profileDir, 'cordis.patch.yml')
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'))
const errors = []

const expectedBundles = ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app']
const profile = manifest.dsh?.profile
if (!profile || manifest.dsh?.bundle) {
  errors.push('profile must declare dsh.profile and must not masquerade as dsh.bundle')
} else {
  if (JSON.stringify(profile.bundles) !== JSON.stringify(expectedBundles)) {
    errors.push(`dsh.profile.bundles must be ${JSON.stringify(expectedBundles)}`)
  }
  if (profile.patchReload !== 'live') errors.push('PureGamma web profile must use patchReload=live')
}

// Keep this tag contract byte-for-byte compatible in meaning with the pinned
// Harness include plugin: !!js values are expression nodes evaluated only when
// their owning loader entry activates. We only validate structure here; we
// never evaluate profile expressions in CI.
const JsExpr = new yaml.Type('tag:yaml.org,2002:js', {
  kind: 'scalar',
  resolve: data => typeof data === 'string',
  construct: data => ({ __jsExpr: data }),
})
const schema = yaml.JSON_SCHEMA.extend(JsExpr)
let patches
try {
  patches = yaml.load(await fs.readFile(patchPath, 'utf8'), { schema })
} catch (error) {
  errors.push(`cordis.patch.yml does not parse with the Harness !!js dialect: ${error.message}`)
}
if (patches !== undefined && !Array.isArray(patches)) {
  errors.push('cordis.patch.yml must be a top-level patch array')
}

const dependencies = manifest.dependencies ?? {}
const requiredPluginNames = new Set()
function collect(entries) {
  if (!Array.isArray(entries)) return
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object') continue
    if (typeof entry.name === 'string' && entry.name.startsWith('@puregamma/dsh-')) requiredPluginNames.add(entry.name)
    collect(entry.insert)
    if (entry.group && Array.isArray(entry.config)) collect(entry.config)
  }
}
collect(patches)

const requireFromProfile = createRequire(manifestPath)
for (const name of requiredPluginNames) {
  if (!(name in dependencies)) {
    errors.push(`profile patch inserts ${name} but package.json does not declare it`)
    continue
  }
  try {
    requireFromProfile.resolve(name)
  } catch {
    errors.push(`profile dependency ${name} cannot resolve from the built profile workspace`)
  }
}

for (const name of Object.keys(dependencies)) {
  if (!name.startsWith('@puregamma/dsh-')) errors.push(`non-plugin dependency ${name} is not allowed in the PureGamma profile`)
}

if (errors.length) {
  console.error('PureGamma Harness profile contract check failed:')
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}
console.log(`PureGamma Harness standalone profile contract passed (${requiredPluginNames.size} mounted plugins, ${profile.bundles.length} Harness bundles).`)
