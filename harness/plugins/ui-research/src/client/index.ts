import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ToolCallViewProps } from '@deepseek-ai/dsh-client-ui-tool/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type { ResearchDocumentPresentation } from '@puregamma/dsh-research'

/**
 * Tool views for the research tools. They show provenance, not content: which
 * research document was read, its as-of and observed time, the source, and
 * whether the provider degraded. The model already received the content; this
 * card is what lets a reader judge how fresh and complete it was.
 */

const NS = 'puregamma.research'
const TOOLS = ['research_today', 'research_overnight', 'research_portfolio_impact', 'research_upcoming_events', 'research_opportunities', 'research_alerts'] as const

const en = {
  reading: 'Reading research…', failed: 'Research read failed', asOf: 'As of', observed: 'Observed', source: 'Source',
  degraded: 'Degraded — some sources were unavailable; treat gaps as unknown', sections: 'Sections', noMeta: 'No presentation data for this call.',
  today: 'Daily research', overnight: 'Overnight research', 'portfolio-impact': 'Portfolio impact', 'upcoming-events': 'Upcoming events', opportunities: 'Opportunities', alerts: 'Alerts',
} as const
const zh: Record<keyof typeof en, string> = {
  reading: '正在读取研究…', failed: '研究读取失败', asOf: '截至', observed: '观测时间', source: '来源',
  degraded: '降级——部分数据源不可用，缺口应视为未知', sections: '包含', noMeta: '此调用没有可展示的数据。',
  today: '每日研究', overnight: '隔夜研究', 'portfolio-impact': '组合影响', 'upcoming-events': '近期事件', opportunities: '机会', alerts: '提醒',
}
type Key = keyof typeof en

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { 'puregamma.research': Key }
}

const KINDS = new Set(['today', 'overnight', 'portfolio-impact', 'upcoming-events', 'opportunities', 'alerts'])

/** Narrow persisted `meta` to the v1 DTO; anything else is treated as absent. */
export function readResearchPresentation(meta: unknown): ResearchDocumentPresentation | null {
  if (!meta || typeof meta !== 'object') return null
  const value = meta as Partial<ResearchDocumentPresentation>
  if (value.schema !== 'puregamma.research.document/v1' || !KINDS.has(String(value.kind)) || typeof value.observedAt !== 'string' || typeof value.source !== 'string') return null
  return { ...value, sections: Array.isArray(value.sections) ? value.sections.filter(item => typeof item === 'string') : [] } as ResearchDocumentPresentation
}

const card: CSSProperties = { display: 'grid', gap: 4, padding: '10px 12px', borderRadius: 10, border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', maxWidth: 560 }
const muted: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', overflowWrap: 'anywhere' }
const warn: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-warning, #b45309)' }

type InjectedProps = { t: (key: Key) => string }

export function ResearchToolView(props: ToolCallViewProps & InjectedProps): ReactElement {
  const { t } = props
  // 0.1.7 toolview owners are phase-based; only `result` carries the settled node.
  if (props.phase !== 'result') return createElement('div', { style: muted, role: 'status' }, t('reading'))
  const { block } = props
  if (block.isError) return createElement('div', { style: { ...card, ...warn }, role: 'status' }, t('failed'))
  const view = readResearchPresentation(block.meta)
  if (!view) return createElement('div', { style: muted }, t('noMeta'))
  return createElement('section', { style: card, 'data-testid': 'puregamma-research-toolview', 'data-degraded': String(view.degraded) },
    createElement('strong', null, t(view.kind as Key)),
    createElement('div', { style: muted }, `${t('asOf')}: ${view.asOf ?? view.observedAt} · ${t('observed')}: ${view.observedAt}`),
    createElement('div', { style: muted }, `${t('source')}: ${view.source}`),
    view.sections.length ? createElement('div', { style: muted }, `${t('sections')}: ${view.sections.join(', ')}`) : null,
    view.degraded ? createElement('div', { style: warn, role: 'status' }, t('degraded')) : null)
}

export const inject = ['slots', 'locale']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-research: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  for (const key of TOOLS) {
    ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({ name: 'tool.call.toolview', key, inject: () => ({ t }) }, ResearchToolView))
  }
}
