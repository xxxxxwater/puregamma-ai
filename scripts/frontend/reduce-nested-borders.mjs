#!/usr/bin/env node
// One-off Round 5 codemod (§9 "把 border 换成留白"): drop neutral borders that
// are nested inside another neutral bordered box in the same JSX tree.
//
// A box with a neutral full border (`border` + border-border-pg/-strong or no
// colour) whose JSX ancestor already draws one is the "5 nested borders"
// pattern. The inner box loses its border and border colour; when it had no
// surface of its own it gets the muted surface tint, so the grouping stays
// visible without a line. Status/accent borders (warnings, selection), side
// rules (border-b/-t dividers) and dynamic class expressions are untouched.
//
// Usage: node scripts/frontend/reduce-nested-borders.mjs [--write] files...
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'apps', 'web')
const ts = createRequire(path.join(web, 'package.json'))('typescript')
const write = process.argv.includes('--write')
const files = process.argv.slice(2).filter(arg => !arg.startsWith('--'))

const NEUTRAL_COLOR = /^(?:hover:|focus-within:)?border-(?:border-pg|border-pg-strong|subtle|default)$/
const isNeutralBox = classes => classes.includes('border') && classes.every(token => !/^(?:[a-z-]+:)?border-(?!border-pg|border-pg-strong|subtle|default|[trblxy]\b|0\b|2\b|dashed|solid|transparent)/.test(token))
const BOXED_COMPONENTS = new Set(['Card', 'ResearchCard', 'PGResearchCard', 'TerminalPanel'])
const CONTROLS = new Set(['input', 'select', 'textarea', 'button', 'a', 'summary'])
const TINTED = /^bg-(?:bg-panel-muted|bg-card-muted|\[var\(--pg-surface-2\)\])$/
const hasSurface = classes => classes.some(token => /^bg-/.test(token))

function staticClassName(node, sf) {
  const attr = node.attributes.properties.find(prop => ts.isJsxAttribute(prop) && prop.name.getText(sf) === 'className')
  const init = attr?.initializer
  if (init && ts.isStringLiteral(init)) return { attr, literal: init }
  if (init && ts.isJsxExpression(init) && init.expression && ts.isNoSubstitutionTemplateLiteral(init.expression)) return { attr, literal: init.expression }
  return undefined
}

let total = 0
const perFile = {}
for (const relative of files) {
  const file = path.resolve(relative)
  const source = readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const edits = []
  const visit = (node, boxedAncestor) => {
    let boxed = boxedAncestor
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const found = staticClassName(node, sf)
      const classes = found ? found.literal.text.split(/\s+/).filter(Boolean) : []
      const tag = node.tagName.getText(sf)
      // Components that draw a card surface themselves count as a box.
      if (BOXED_COMPONENTS.has(tag)) return true
      // Only intrinsic elements (a component's className may style something
      // else), and never controls: an input's or link's outline is affordance.
      const intrinsic = /^[a-z]/.test(tag) && !CONTROLS.has(tag)
      if (found && intrinsic && isNeutralBox(classes)) {
        // A tinted well (muted surface) is already grouped by its tint; a line
        // around it is the second signal for the same thing.
        const tinted = classes.some(token => TINTED.test(token))
        if (boxedAncestor || tinted) {
          const kept = classes.filter(token => token !== 'border' && !NEUTRAL_COLOR.test(token))
          if (!hasSurface(classes)) kept.push('bg-bg-panel-muted')
          const quote = ts.isStringLiteral(found.literal) ? '"' : '`'
          edits.push({ start: found.literal.getStart(sf), end: found.literal.getEnd(), text: `${quote}${kept.join(' ')}${quote}` })
          total++
          perFile[path.relative(web, file)] = (perFile[path.relative(web, file)] ?? 0) + 1
        } else {
          boxed = true
        }
      }
      // Children of this element are visited through its JsxElement parent below.
      return boxed
    }
    if (ts.isJsxElement(node)) {
      const childBoxed = visit(node.openingElement, boxedAncestor)
      for (const child of node.children) visit(child, childBoxed)
      return boxedAncestor
    }
    if (ts.isJsxSelfClosingElement(node)) return visit(node, boxedAncestor)
    // Crossing into a function (e.g. a .map callback) keeps the JSX ancestry;
    // crossing into a new component declaration resets it.
    const resets = ts.isFunctionDeclaration(node) || (ts.isVariableDeclaration(node) && node.initializer && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer)) && /^[A-Z]/.test(node.name.getText(sf)))
    ts.forEachChild(node, child => { visit(child, resets ? false : boxedAncestor) })
    return boxedAncestor
  }
  visit(sf, false)
  if (!edits.length || !write) continue
  let out = source
  for (const edit of edits.sort((a, b) => b.start - a.start)) out = out.slice(0, edit.start) + edit.text + out.slice(edit.end)
  writeFileSync(file, out)
}
console.log(JSON.stringify({ removed: total, files: perFile }, null, 1))
