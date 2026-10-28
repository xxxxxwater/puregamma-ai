import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ToolCallViewProps } from '@deepseek-ai/dsh-client-ui-tool/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type { MemoryDocumentPresentation } from '@puregamma/dsh-memory'

/**
 * Tool views for the memory tools. They show what was read (settings, items,
 * proposals, export) and how many entries, never the entries themselves:
 * memory is personal, and its contents stay in the Memory surface the user
 * controls, with consent and deletion.
 */
const NS = 'puregamma.memory'
const TOOLS = ['memory_settings',  'memory_items',  'memory_proposals',  'memory_export_descriptor'] as const
const en = {
  reading: 'Reading memory…', failed: 'Memory read failed', observed: 'Observed', source: 'Source', count: 'Entries',
  private: 'Contents are not shown here; review or delete them in Memory settings.', noMeta: 'No presentation data for this call.',
  settings: 'Memory settings', items: 'Memory items', proposals: 'Memory proposals', proposal: 'Memory proposal', mutation: 'Memory change', export: 'Memory export',
} as const
const zh: Record<keyof typeof en, string> = {
  reading: '正在读取记忆…', failed: '记忆读取失败', observed: '观测时间', source: '来源', count: '条目数',
  private: '此处不显示内容；请在记忆设置中查看或删除。', noMeta: '此调用没有可展示的数据。',
  settings: '记忆设置', items: '记忆条目', proposals: '记忆提议', proposal: '记忆提议', mutation: '记忆变更', export: '记忆导出',
}
type Key = keyof typeof en
declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { 'puregamma.memory': Key }
}
const KINDS = new Set(['settings', 'items', 'proposals', 'proposal', 'mutation', 'export'])

export function readPresentation(meta: unknown): MemoryDocumentPresentation | null {
  if (!meta || typeof meta !== 'object') return null
  const value = meta as Partial<MemoryDocumentPresentation>
  if (value.schema !== 'puregamma.memory.document/v1' || !KINDS.has(String(value.kind)) || typeof value.observedAt !== 'string' || typeof value.source !== 'string') return null
  return value as MemoryDocumentPresentation
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
  return createElement('section', { style: card, 'data-testid': 'puregamma-memory-toolview' },
    createElement('strong', null, t(view.kind as Key)),
    createElement('div', { style: muted }, `${t('observed')}: ${view.observedAt} · ${t('source')}: ${view.source}`),
    typeof view.count === 'number' ? createElement('div', { style: muted }, `${t('count')}: ${view.count}`) : null,
    createElement('div', { style: muted }, t('private')))
}

export const inject = ['slots', 'locale']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-memory: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  for (const key of TOOLS) {
    ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({ name: 'tool.call.toolview', key, inject: () => ({ t }) }, ToolView))
  }
}
