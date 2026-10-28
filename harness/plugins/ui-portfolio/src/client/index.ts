import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ToolCallViewProps } from '@deepseek-ai/dsh-client-ui-tool/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type { PortfolioNavPresentation } from '@puregamma/dsh-portfolio'

/**
 * Tool views for the portfolio tools (`portfolio_nav`, `portfolio_snapshot`).
 *
 * The view reads only the tool result's `meta` (`output.presentationMeta`,
 * never model-visible). It states the amount with its currency, when the
 * server observed it, and whether it is stale or unavailable. A missing NAV is
 * shown as unavailable with the server's reason, never as zero. Removing this
 * plugin falls back to DSH's generic tool row; nothing in the shell changes.
 */

const NS = 'puregamma.portfolio'
const TOOLS = ['portfolio_nav', 'portfolio_snapshot'] as const

const en = {
  title: 'Portfolio NAV', reading: 'Reading portfolio…', failed: 'Portfolio read failed', unavailable: 'NAV unavailable',
  stale: 'Stale — not a current value', observed: 'Observed', prices: 'Prices as of', cash: 'Cash', positions: 'Positions',
  version: 'Calculation', noReason: 'No connected portfolio snapshot', noMeta: 'No presentation data for this call.',
} as const
const zh: Record<keyof typeof en, string> = {
  title: '组合 NAV', reading: '正在读取组合…', failed: '组合读取失败', unavailable: 'NAV 不可用',
  stale: '已过期——不是当前值', observed: '观测时间', prices: '价格时间', cash: '现金', positions: '持仓数',
  version: '计算版本', noReason: '没有已连接的组合快照', noMeta: '此调用没有可展示的数据。',
}
type Key = keyof typeof en

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { 'puregamma.portfolio': Key }
}

/** Narrow persisted `meta` to the v1 DTO; anything else is treated as absent. */
export function readNavPresentation(meta: unknown): PortfolioNavPresentation | null {
  if (!meta || typeof meta !== 'object') return null
  const value = meta as Partial<PortfolioNavPresentation>
  if (value.schema !== 'puregamma.portfolio.nav/v1' || typeof value.available !== 'boolean' || typeof value.currency !== 'string' || typeof value.observedAt !== 'string') return null
  return value as PortfolioNavPresentation
}

const card: CSSProperties = { display: 'grid', gap: 6, padding: '10px 12px', borderRadius: 10, border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', maxWidth: 560 }
const muted: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))' }
const amount: CSSProperties = { fontSize: 20, fontWeight: 600, fontVariantNumeric: 'tabular-nums', overflowWrap: 'anywhere' }
const warn: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-warning, #b45309)' }

function fmt(value: string | null): string | null {
  if (value === null) return null
  // Group digits as text; never parse money through binary floats.
  const [whole, fraction] = value.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return fraction === undefined ? grouped : `${grouped}.${fraction}`
}

type InjectedProps = { t: (key: Key) => string }

export function NavToolView(props: ToolCallViewProps & InjectedProps): ReactElement {
  const { block, t } = props
  const settled = 'kind' in block && block.kind === 'tool-result'
  if (!settled) return createElement('div', { style: muted, role: 'status' }, t('reading'))
  if (block.isError) return createElement('div', { style: { ...card, ...warn }, role: 'status' }, t('failed'))
  const view = readNavPresentation(block.meta)
  if (!view) return createElement('div', { style: muted }, t('noMeta'))
  const rows: ReactElement[] = []
  const add = (label: string, value: string | null) => {
    if (value !== null) rows.push(createElement('div', { key: label, style: muted }, `${label}: ${value}`))
  }
  if (!view.available || view.nav === null) {
    return createElement('section', { style: card, 'data-testid': 'puregamma-nav-toolview', 'data-state': 'unavailable' },
      createElement('strong', null, t('unavailable')),
      createElement('div', { style: muted }, view.reason ?? t('noReason')),
      createElement('div', { style: muted }, `${t('observed')}: ${view.observedAt}`))
  }
  add(t('cash'), view.cash === null ? null : `${fmt(view.cash)} ${view.currency}`)
  add(t('positions'), view.positions === null ? null : String(view.positions))
  add(t('observed'), view.observedAt)
  add(t('prices'), view.priceObservedAt)
  add(t('version'), view.calculationVersion)
  return createElement('section', { style: card, 'data-testid': 'puregamma-nav-toolview', 'data-state': view.stale ? 'stale' : 'live' },
    createElement('div', { style: muted }, t('title')),
    createElement('div', { style: amount }, `${fmt(view.nav)} ${view.currency}`),
    view.stale ? createElement('div', { style: warn, role: 'status' }, t('stale')) : null,
    ...rows)
}

export const inject = ['slots', 'locale']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-portfolio: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  for (const key of TOOLS) {
    ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({ name: 'tool.call.toolview', key, inject: () => ({ t }) }, NavToolView))
  }
}
