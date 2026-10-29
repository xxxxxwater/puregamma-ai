#!/usr/bin/env node
// Round 5 density counters (docs/frontend/UI_DENSITY_AUDIT.md §1), measured
// over apps/web/{app,components,lib,plugins} *.ts(x). Usage:
//   node scripts/frontend/ui-density-counts.mjs [--json] [--by-file <metric>]
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'apps', 'web')
const roots = ['app', 'components', 'lib', 'plugins']
const files = []
const walk = dir => {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name)
    if (name === 'node_modules' || name.startsWith('.next')) continue
    if (statSync(full).isDirectory()) walk(full)
    else if (/\.tsx?$/.test(name)) files.push(full)
  }
}
for (const root of roots) walk(path.join(web, root))

export const METRICS = {
  rawButton: /<button\b/g,
  buttonComponent: /<Button\b/g,
  // Border-WIDTH utilities (a drawn border): border, border-t, border-x-2,
  // border-[0.5px], with or without variants. Colour utilities such as
  // border-border-pg only tint a border that one of these draws, so they are
  // not counted (the audit's 818 counted bordered elements, not colour tokens).
  borderUtility: /(?<=["'`\s{(])(?:[a-z-]+:)*border(?:-[trblxyse])?(?:-(?:0|2|4|8|\[[^\]\s]+\]))?(?=["'`\s})])/g,
  arbitraryTextPx: /\btext-\[\d+(?:\.\d+)?px\]/g,
  arbitraryLeading: /\bleading-\[[^\]]+\]/g,
  roundedUtility: /(?<=["'`\s{(])(?:[a-z-]+:)*rounded(?:-[a-z0-9[\]/.%-]+)?(?=["'`\s})])/g,
}

const counts = {}
const byFile = {}
for (const [metric, pattern] of Object.entries(METRICS)) {
  counts[metric] = 0
  byFile[metric] = []
  for (const file of files) {
    const n = (readFileSync(file, 'utf8').match(pattern) ?? []).length
    counts[metric] += n
    if (n) byFile[metric].push([n, path.relative(web, file)])
  }
  byFile[metric].sort((a, b) => b[0] - a[0])
}

const args = process.argv.slice(2)
if (args.includes('--json')) console.log(JSON.stringify(counts))
else if (args[0] === '--by-file') for (const [n, file] of byFile[args[1]].slice(0, Number(args[2] ?? 15))) console.log(String(n).padStart(4), file)
else for (const [metric, value] of Object.entries(counts)) console.log(metric.padEnd(18), value)
