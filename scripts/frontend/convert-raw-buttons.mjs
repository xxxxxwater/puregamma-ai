#!/usr/bin/env node
// One-off Round 5 codemod: raw <button> with a STATIC class string -> <Button>.
//
// Conservative by design:
// - only `className="..."` string literals (dynamic class expressions keep
//   their raw <button>, because a state-dependent bg/border would fight the
//   variant's colours);
// - geometry the call site chose (height, padding, radius, text size,
//   justify, display, width) is kept verbatim, so layout does not move; only
//   the colour/border/transition/focus classes the variant owns are removed;
// - bespoke colours (status-*, accent, ocean, overlays, inverse-on-custom)
//   are skipped and reported, never guessed.
// Every attribute (type, aria-*, data-testid, title, ref, handlers) is kept,
// so role/name selectors and focus behaviour are unchanged.
//
// Usage: node scripts/frontend/convert-raw-buttons.mjs [--write] [files...]
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'apps', 'web')
const ts = createRequire(path.join(web, 'package.json'))('typescript')
const write = process.argv.includes('--write')
const files = process.argv.slice(2).filter(arg => !arg.startsWith('--'))

const NEUTRAL_BORDER = /^(?:border-border-pg|border-border-pg-strong|border-transparent|border-subtle|border-default|border-\[var\(--pg-border-[a-z]+\)\])$/
const NEUTRAL_BG = /^(?:bg-bg-panel|bg-bg-panel-muted|bg-bg-card|bg-bg-card-muted|bg-transparent|bg-\[var\(--pg-surface-(?:1|2|hover)\)\])$/
const NEUTRAL_TEXT = /^(?:text-text-pg|text-text-pg-muted|text-text-pg-dim|text-foreground|text-text-primary|text-text-secondary)$/
const INVERSE_BG = /^(?:bg-\[var\(--pg-surface-inverse\)\]|bg-text-pg|bg-foreground)$/
const INVERSE_TEXT = /^(?:text-\[var\(--pg-text-inverse\)\]|text-bg-app|text-bg-panel)$/
const OWNED = /^(?:transition(?:-[a-z[\],-]+)?|duration-\d+|ease-[a-z-]+|focus-visible:.*|focus:outline-none|outline-none|font-medium|hover:-translate-y-0\.5|disabled:hover:translate-y-0)$/

function classify(classes) {
  const keep = []
  let border = false, neutralBorder = true, inverse = false, negative = false, bespoke = []
  for (const token of classes) {
    const bare = token.replace(/^(?:hover|focus|active|group-hover):/, '')
    const stateful = bare !== token
    if (/^border(?:-[trblxy])?(?:-(?:0|2|\[[^\]]+\]))?$/.test(token)) { border = true; continue }
    if (/^border-/.test(bare) && !/^border-(?:[trblxy])?(?:-(?:0|2))?$/.test(bare)) {
      if (NEUTRAL_BORDER.test(bare)) continue
      if (/status-negative|danger/.test(bare)) { negative = true; continue }
      neutralBorder = false; bespoke.push(token); continue
    }
    if (/^bg-/.test(bare)) {
      if (NEUTRAL_BG.test(bare) || (stateful && /^bg-(?:bg-|\[var\(--pg-surface)/.test(bare))) continue
      if (!stateful && INVERSE_BG.test(bare)) { inverse = true; continue }
      bespoke.push(token); continue
    }
    if (/^text-/.test(bare) && !/^text-(?:\d|xs|sm|base|lg|xl|2xl|2xs|left|right|center|start|end|\[\d)/.test(bare)) {
      if (NEUTRAL_TEXT.test(bare)) continue
      if (INVERSE_TEXT.test(bare)) { inverse = true; continue }
      if (/status-negative/.test(bare)) { negative = true; continue }
      bespoke.push(token); continue
    }
    if (/^(?:shadow|hover:shadow)/.test(token)) continue
    if (OWNED.test(token)) continue
    if (/accent|ocean|status-|opacity-0|sr-only/.test(token)) { bespoke.push(token); continue }
    keep.push(token)
  }
  if (bespoke.length) return { skip: `bespoke colours: ${bespoke.join(' ')}` }
  if (inverse && negative) return { skip: 'inverse and negative at once' }
  const variant = inverse ? 'primary' : negative ? 'danger' : border && neutralBorder ? 'secondary' : 'ghost'
  const text = keep.find(token => /^text-(?:xs|11|12|sm|13|14|base|16)$/.test(token))
  const size = /^text-(?:xs|11|12)$/.test(text ?? '') ? 'sm' : keep.some(token => /^(?:min-h|h)-(?:11|12)$/.test(token)) ? 'lg' : 'md'
  return { variant, size, className: keep.join(' ') }
}

const report = { converted: 0, skipped: [], files: {} }
for (const relative of files) {
  const file = path.resolve(relative)
  const source = readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const edits = []
  const visit = node => {
    if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && node.tagName.getText(sf) === 'button') {
      const attr = node.attributes.properties.find(prop => ts.isJsxAttribute(prop) && prop.name.getText(sf) === 'className')
      const where = `${path.relative(web, file)}:${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1}`
      let classes = []
      if (attr) {
        const init = attr.initializer
        const literal = init && ts.isStringLiteral(init) ? init : init && ts.isJsxExpression(init) && init.expression && ts.isNoSubstitutionTemplateLiteral(init.expression) ? init.expression : undefined
        if (!literal) { report.skipped.push(`${where} dynamic className`); return ts.forEachChild(node, visit) }
        classes = literal.text.split(/\s+/).filter(Boolean)
      }
      const result = classify(classes)
      if (result.skip) { report.skipped.push(`${where} ${result.skip}`); return ts.forEachChild(node, visit) }
      const props = [`variant="${result.variant}"`, ...(result.size === 'md' ? [] : [`size="${result.size}"`])]
      edits.push({ start: node.tagName.getStart(sf), end: node.tagName.getEnd(), text: `Button ${props.join(' ')}` })
      if (attr) {
        // Dropping the attribute also drops the one space before it.
        const start = result.className ? attr.getStart(sf) : attr.getStart(sf) - (source[attr.getStart(sf) - 1] === ' ' ? 1 : 0)
        edits.push({ start, end: attr.getEnd(), text: result.className ? `className="${result.className}"` : '' })
      }
      if (ts.isJsxOpeningElement(node)) {
        const closing = node.parent.closingElement
        edits.push({ start: closing.tagName.getStart(sf), end: closing.tagName.getEnd(), text: 'Button' })
      }
      report.converted++
      report.files[path.relative(web, file)] = (report.files[path.relative(web, file)] ?? 0) + 1
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  if (!edits.length) continue
  // Import placement from the AST, never from text: a string literal may
  // contain "import ... from" (e.g. a code sample shown to users).
  const imports = sf.statements.filter(ts.isImportDeclaration)
  const uiImport = imports.find(decl => ts.isStringLiteral(decl.moduleSpecifier) && decl.moduleSpecifier.text === '@/components/ui')
  const named = uiImport?.importClause?.namedBindings
  const hasButton = named && ts.isNamedImports(named) && named.elements.some(element => element.name.text === 'Button')
  if (!hasButton) {
    if (named && ts.isNamedImports(named)) {
      const last = named.elements[named.elements.length - 1]
      edits.push({ start: last.getEnd(), end: last.getEnd(), text: ', Button' })
    } else {
      const at = imports.length ? imports[imports.length - 1].getEnd() : 0
      edits.push({ start: at, end: at, text: '\nimport { Button } from "@/components/ui";' })
    }
  }
  let out = source
  for (const edit of edits.sort((a, b) => b.start - a.start)) out = out.slice(0, edit.start) + edit.text + out.slice(edit.end)
  if (write) writeFileSync(file, out)
}
console.log(JSON.stringify({ converted: report.converted, files: report.files, skipped: report.skipped.length }, null, 1))
if (process.argv.includes('--verbose')) for (const line of report.skipped) console.log('skip', line)
