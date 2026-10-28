import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ToolCallViewProps } from '@deepseek-ai/dsh-client-ui-tool/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type { BacktestDocumentPresentation } from '@puregamma/dsh-backtest'

/**
 * Tool views for the backtest tools: which document, the run and its status,
 * and the metrics the backtest service reported, copied verbatim. Every card
 * says it is a simulation on historical data, never a forecast or a signal.
 */
const NS = 'puregamma.backtest'
const TOOLS = ['backtest_status',  'backtest_compile',  'backtest_run',  'backtest_runs',  'backtest_result',  'backtest_cancel',  'backtest_export',  'backtest_save_strategy'] as const
const en = {
  reading: 'Reading backtest…', failed: 'Backtest call failed', observed: 'Observed', source: 'Source', run: 'Run', status: 'Status',
  simulated: 'Simulated on historical data — not a forecast or a trading signal', noMeta: 'No presentation data for this call.',
  status_kind: 'Backtest service', spec: 'Compiled strategy spec', run_kind: 'Backtest run', runs: 'Backtest runs', artifact: 'Backtest artifact', strategy: 'Saved strategy', 'data-status': 'Data coverage',
} as const
const zh: Record<keyof typeof en, string> = {
  reading: '正在读取回测…', failed: '回测调用失败', observed: '观测时间', source: '来源', run: '运行', status: '状态',
  simulated: '基于历史数据的模拟——不是预测，也不是交易信号', noMeta: '此调用没有可展示的数据。',
  status_kind: '回测服务', spec: '已编译策略', run_kind: '回测运行', runs: '回测列表', artifact: '回测产物', strategy: '已保存策略', 'data-status': '数据覆盖',
}
type Key = keyof typeof en
declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { 'puregamma.backtest': Key }
}
const KINDS = new Set(['status', 'spec', 'run', 'runs', 'artifact', 'strategy', 'data-status'])
const LABEL: Record<string, Key> = { status: 'status_kind', spec: 'spec', run: 'run_kind', runs: 'runs', artifact: 'artifact', strategy: 'strategy', 'data-status': 'data-status' }

export function readPresentation(meta: unknown): BacktestDocumentPresentation | null {
  if (!meta || typeof meta !== 'object') return null
  const value = meta as Partial<BacktestDocumentPresentation>
  if (value.schema !== 'puregamma.backtest.document/v1' || !KINDS.has(String(value.kind)) || typeof value.observedAt !== 'string' || typeof value.source !== 'string') return null
  const metrics = Array.isArray(value.metrics) ? value.metrics.filter(item => item && typeof item.name === 'string' && typeof item.value === 'number' && Number.isFinite(item.value)) : []
  return { ...value, metrics } as BacktestDocumentPresentation
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
  return createElement('section', { style: card, 'data-testid': 'puregamma-backtest-toolview' },
    createElement('strong', null, t(LABEL[view.kind])),
    createElement('div', { style: muted }, `${t('observed')}: ${view.observedAt} · ${t('source')}: ${view.source}`),
    view.runId || view.status ? createElement('div', { style: muted }, [view.runId ? `${t('run')}: ${view.runId}` : '', view.status ? `${t('status')}: ${view.status}` : ''].filter(Boolean).join(' · ')) : null,
    view.metrics.length ? createElement('div', { style: { ...muted, fontVariantNumeric: 'tabular-nums' } }, view.metrics.map(metric => `${metric.name} ${metric.value}`).join(' · ')) : null,
    createElement('div', { style: muted }, t('simulated')))
}

export const inject = ['slots', 'locale']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-backtest: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  for (const key of TOOLS) {
    ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({ name: 'tool.call.toolview', key, inject: () => ({ t }) }, ToolView))
  }
}
