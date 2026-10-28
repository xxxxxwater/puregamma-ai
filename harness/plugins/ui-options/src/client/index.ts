import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ToolCallViewProps } from '@deepseek-ai/dsh-client-ui-tool/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type { OptionsDocumentPresentation } from '@puregamma/dsh-options'

/**
 * Tool views for the options research tools: which read, underlying and
 * provider, how fresh, provider state, and how many rows came back. Options
 * reads are research only; the card says execution is disabled because the
 * service contract pins `executionEnabled: false`.
 */
const NS = 'puregamma.options'
const TOOLS = ['options_chain',  'options_long_gamma',  'options_surface',  'options_surface_tickers',  'options_earnings_gamma'] as const
const en = {
  reading: 'Reading options data…', failed: 'Options read failed', observed: 'Observed', source: 'Source', rows: 'Rows',
  provider: 'Provider', researchOnly: 'Research only — execution disabled', degraded: 'Provider degraded — treat gaps as unknown',
  unavailable: 'Provider unavailable — no data was returned', noMeta: 'No presentation data for this call.',
  chain: 'Options chain', 'long-gamma': 'Long Gamma candidates', surface: 'Volatility surface', 'surface-tickers': 'Surface tickers', 'earnings-gamma': 'Earnings gamma',
} as const
const zh: Record<keyof typeof en, string> = {
  reading: '正在读取期权数据…', failed: '期权读取失败', observed: '观测时间', source: '来源', rows: '条目',
  provider: '数据商', researchOnly: '仅研究——执行已禁用', degraded: '数据源降级——缺口应视为未知',
  unavailable: '数据源不可用——没有返回数据', noMeta: '此调用没有可展示的数据。',
  chain: '期权链', 'long-gamma': 'Long Gamma 候选', surface: '波动率曲面', 'surface-tickers': '曲面标的', 'earnings-gamma': '财报 Gamma',
}
type Key = keyof typeof en
declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { 'puregamma.options': Key }
}
const KINDS = new Set(['chain', 'long-gamma', 'surface', 'surface-tickers', 'earnings-gamma'])
const STATES = new Set(['healthy', 'degraded', 'unavailable'])

export function readPresentation(meta: unknown): OptionsDocumentPresentation | null {
  if (!meta || typeof meta !== 'object') return null
  const value = meta as Partial<OptionsDocumentPresentation>
  if (value.schema !== 'puregamma.options.document/v1' || !KINDS.has(String(value.kind)) || !STATES.has(String(value.state)) || typeof value.observedAt !== 'string' || typeof value.source !== 'string') return null
  return value as OptionsDocumentPresentation
}
const card: CSSProperties = { display: 'grid', gap: 4, padding: '10px 12px', borderRadius: 10, border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', maxWidth: 560 }
const muted: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', overflowWrap: 'anywhere' }
const warn: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-warning, #b45309)' }

type InjectedProps = { t: (key: Key) => string }

export function ToolView(props: ToolCallViewProps & InjectedProps): ReactElement {
  const { t } = props
  // 0.1.7 toolview owners are phase-based; only `result` carries the settled node.
  if (props.phase !== 'result') return createElement('div', { style: muted, role: 'status' }, t('reading'))
  const { block } = props
  if (block.isError) return createElement('div', { style: { ...card, ...warn }, role: 'status' }, t('failed'))
  const view = readPresentation(block.meta)
  if (!view) return createElement('div', { style: muted }, t('noMeta'))
  return createElement('section', { style: card, 'data-testid': 'puregamma-options-toolview', 'data-state': view.state },
    createElement('strong', null, `${t(view.kind as Key)}${view.underlying ? ` · ${view.underlying}` : ''}`),
    createElement('div', { style: muted }, `${t('observed')}: ${view.observedAt} · ${t('source')}: ${view.source}`),
    view.provider ? createElement('div', { style: muted }, `${t('provider')}: ${view.provider}`) : null,
    view.size !== null ? createElement('div', { style: muted }, `${t('rows')}: ${view.size}`) : null,
    view.state === 'degraded' ? createElement('div', { style: warn, role: 'status' }, t('degraded')) : null,
    view.state === 'unavailable' ? createElement('div', { style: warn, role: 'status' }, t('unavailable')) : null,
    createElement('div', { style: muted }, t('researchOnly')))
}

export const inject = ['slots', 'locale']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-options: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  for (const key of TOOLS) {
    ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({ name: 'tool.call.toolview', key, inject: () => ({ t }) }, ToolView))
  }
}
