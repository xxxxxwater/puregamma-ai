import { createElement } from 'react'
import type { CSSProperties, ReactElement, ReactNode } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ResourceSnapshot, UseResource } from '@deepseek-ai/dsh-client-resources/client'
import type { UseSidebarRightTabInfo } from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@puregamma/dsh-client-remotes/client'
import type {} from '@puregamma/dsh-client-gateway/remote'
import type {
  PureGammaBacktestArtifactView, PureGammaBacktestRunsView, PureGammaResearchArtifactsView, PureGammaResearchRunsView,
} from '@puregamma/dsh-client-gateway'
import { PROTOCOL, followResearchRun, pollResource, resourceAddress, resourceId, type Freshness, type LiveResearchRunView, type ProtocolName } from './model.js'

export { PROTOCOL, backoff, followResearchRun, pollResource, resourceAddress, resourceId } from './model.js'
export type { Freshness, LiveResearchRunView, ResearchRunRemote } from './model.js'

/**
 * Right-sidebar resource views for research runs, research artifacts and
 * backtest artifacts, plus one guide page listing recent runs.
 *
 * Read-only by construction: the only Remote calls are the gateway's reads,
 * there is no cancel/retry/export button, and no request leaves the browser
 * except through the Harness Remote carrier (the Host holds the bearer).
 * Honesty rules: loading, failed, unavailable and stale are distinct states
 * with their reason; a value the server did not report is "not reported",
 * never 0 or a blank.
 */

const NS = 'puregamma.researchResources'
const PLUGIN = '@puregamma/dsh-ui-research-resources'
export const TAB_IDS = {
  researchRun: `${PLUGIN}/research-run`,
  researchArtifact: `${PLUGIN}/research-artifact`,
  backtestArtifact: `${PLUGIN}/backtest-artifact`,
  index: `${PLUGIN}/index`,
} as const
export const INDEX_KIND = 'puregamma-research-index'
const INDEX_ADDRESS = `dsh-resource://${PROTOCOL.researchIndex}/recent`
const BACKTEST_INDEX_ADDRESS = `dsh-resource://${PROTOCOL.backtestIndex}/recent`

const en = {
  guide: 'Research & backtests', guideDescription: 'Recent research runs and backtest artifacts',
  indexTitle: 'Research & backtests', researchRuns: 'Research runs', backtestRuns: 'Backtest runs',
  runTitle: 'Research run', artifactTitle: 'Research artifacts', backtestTitle: 'Backtest artifacts',
  loading: 'Loading…', failed: 'Read failed', unavailable: 'Unavailable', notReported: 'not reported',
  stale: 'Showing the last successful read; reconnecting', staleSince: 'stale since', live: 'Following live', ended: 'Final state',
  status: 'Status', verification: 'Verification', created: 'Created', updated: 'Updated', completed: 'Completed', evidence: 'Evidence items',
  citations: 'Citations', credits: 'Credits used', error: 'Error', summary: 'Summary', source: 'Source', observed: 'Observed',
  openArtifacts: 'Open artifacts', open: 'Open', noRuns: 'The server reports no runs yet.', noArtifacts: 'The server reports no artifacts for this run.',
  noEvidence: 'The server reports no evidence for this run.', evidenceUnavailable: 'Evidence is unavailable right now.', truncated: 'Report shortened for display.',
  metrics: 'Reported metrics', noMetrics: 'The server reports no metrics for this run.', files: 'Files', size: 'bytes', checksum: 'checksum',
  window: 'Window', engine: 'Engine', asset: 'Asset', legacy: 'Legacy backtest-lab run',
  simulated: 'Simulated on historical data — not a forecast or a trading signal',
} as const
const zh: Record<keyof typeof en, string> = {
  guide: '研究与回测', guideDescription: '最近的研究任务与回测产物',
  indexTitle: '研究与回测', researchRuns: '研究任务', backtestRuns: '回测任务',
  runTitle: '研究任务', artifactTitle: '研究产物', backtestTitle: '回测产物',
  loading: '正在读取…', failed: '读取失败', unavailable: '不可用', notReported: '未报告',
  stale: '显示的是上一次成功读取的结果，正在重新连接', staleSince: '过期起始', live: '实时跟踪中', ended: '最终状态',
  status: '状态', verification: '核验', created: '创建', updated: '更新', completed: '完成', evidence: '证据条数',
  citations: '引用数', credits: '消耗 Credits', error: '错误', summary: '摘要', source: '来源', observed: '观测时间',
  openArtifacts: '查看产物', open: '打开', noRuns: '服务端暂无任务记录。', noArtifacts: '服务端没有报告此任务的产物。',
  noEvidence: '服务端没有报告此任务的证据。', evidenceUnavailable: '证据暂时不可用。', truncated: '报告已截断显示。',
  metrics: '报告的指标', noMetrics: '服务端没有报告此任务的指标。', files: '文件', size: '字节', checksum: '校验和',
  window: '区间', engine: '引擎', asset: '资产', legacy: '旧版 backtest-lab 任务',
  simulated: '基于历史数据的模拟——不是预测，也不是交易信号',
}
export type Key = keyof typeof en

type Live<T> = T & Freshness
declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface ResourceProtocolMap {
    'puregamma-research-run': LiveResearchRunView
    'puregamma-research-artifact': Live<PureGammaResearchArtifactsView>
    'puregamma-backtest-artifact': Live<PureGammaBacktestArtifactView>
    'puregamma-research-index': Live<PureGammaResearchRunsView>
    'puregamma-backtest-index': Live<PureGammaBacktestRunsView>
  }
  interface LocaleNamespaceMap { 'puregamma.researchResources': Key }
}

const page: CSSProperties = { display: 'grid', gap: 12, padding: 16, alignContent: 'start', overflowY: 'auto', height: '100%', boxSizing: 'border-box' }
const muted: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', overflowWrap: 'anywhere' }
const warn: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-warning, #b45309)' }
const grid: CSSProperties = { display: 'grid', gridTemplateColumns: 'minmax(96px, .7fr) minmax(120px, 1.6fr)', gap: '6px 14px', fontSize: 13 }
const section: CSSProperties = { display: 'grid', gap: 8, borderTop: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', paddingTop: 10 }
const button: CSSProperties = { justifySelf: 'start', font: 'inherit', fontSize: 12, padding: '4px 10px', borderRadius: 6, cursor: 'pointer', border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.35))', background: 'transparent', color: 'inherit' }

type T = (key: Key) => string
export interface BodyProps { useTabInfo: UseSidebarRightTabInfo; useResource: UseResource; t: T }

function field(label: string, value: string | number | undefined, t: T): ReactElement[] {
  return [
    createElement('div', { key: `${label}:l`, style: muted }, label),
    createElement('div', { key: `${label}:v`, ...(value === undefined ? { style: muted, 'data-missing': 'true' } : {}) }, value === undefined ? t('notReported') : String(value)),
  ]
}

/**
 * The shared state ladder: loading → failed (no value) → unavailable (with the
 * provider's reason) → value, with a stale banner when the value is a last
 * known copy. `render` only ever sees an available value.
 */
function stateful<V extends { available: boolean; reason?: string; observedAt: string; source: string } & Freshness>(snapshot: ResourceSnapshot<V>, t: T, testId: string, render: (value: V) => ReactNode): ReactElement {
  const value = snapshot.value
  if (snapshot.status === 'none' || (snapshot.status === 'loading' && value === undefined)) {
    return createElement('div', { style: page, 'data-testid': testId, 'data-state': 'loading', role: 'status' }, createElement('span', { style: muted }, t('loading')))
  }
  if (value === undefined) {
    return createElement('div', { style: page, 'data-testid': testId, 'data-state': 'failed', role: 'alert' },
      createElement('strong', null, t('failed')),
      snapshot.failure?.message ? createElement('span', { style: muted }, snapshot.failure.message) : null)
  }
  if (!value.available) {
    return createElement('div', { style: page, 'data-testid': testId, 'data-state': 'unavailable', role: 'status' },
      createElement('strong', null, t('unavailable')),
      value.reason ? createElement('span', { style: muted }, value.reason) : null)
  }
  const stale = value.stale === true || snapshot.status === 'failed'
  const staleReason = value.staleReason ?? snapshot.failure?.message
  return createElement('div', { style: page, 'data-testid': testId, 'data-state': stale ? 'stale' : 'live' },
    stale ? createElement('div', { style: warn, role: 'status' }, [t('stale'), value.staleSince ? `${t('staleSince')}: ${value.staleSince}` : '', staleReason ?? ''].filter(Boolean).join(' · ')) : null,
    render(value),
    createElement('div', { style: muted }, `${t('source')}: ${value.source} · ${t('observed')}: ${value.observedAt}`))
}

export function ResearchRunBody({ useTabInfo, useResource, t }: BodyProps): ReactElement {
  const { tab } = useTabInfo()
  const snapshot = useResource<'puregamma-research-run'>(tab.contentId)
  return stateful(snapshot, t, 'puregamma-research-run', view => {
    const run = view.run!
    return [
      createElement('header', { key: 'h', style: { display: 'grid', gap: 4 } },
        createElement('strong', null, run.name ?? run.id),
        createElement('span', { style: muted, 'data-connection': view.connection }, view.connection === 'ended' ? t('ended') : view.connection === 'live' ? t('live') : t('stale'))),
      createElement('div', { key: 'g', style: grid },
        ...field(t('status'), run.status, t),
        ...field(t('verification'), run.verification, t),
        ...field(t('created'), run.createdAt, t),
        ...field(t('updated'), run.updatedAt, t),
        ...field(t('evidence'), run.evidenceCount, t),
        ...field(t('citations'), run.citationCount, t),
        ...field(t('credits'), run.creditsUsed, t)),
      run.errorMessage ? createElement('div', { key: 'e', style: warn, role: 'alert' }, `${t('error')}: ${run.errorMessage}`) : null,
      run.summary ? createElement('p', { key: 's', style: { margin: 0, fontSize: 13, whiteSpace: 'pre-wrap' } }, run.summary) : null,
      run.disclaimer ? createElement('p', { key: 'd', style: { ...muted, margin: 0 } }, run.disclaimer) : null,
      createElement('button', { key: 'o', type: 'button', style: button, onClick: () => tab.actions.openResource(resourceAddress(PROTOCOL.researchArtifact, run.id)) }, t('openArtifacts')),
    ]
  })
}

export function ResearchArtifactBody({ useTabInfo, useResource, t }: BodyProps): ReactElement {
  const { tab } = useTabInfo()
  const snapshot = useResource<'puregamma-research-artifact'>(tab.contentId)
  return stateful(snapshot, t, 'puregamma-research-artifact', view => [
    createElement('strong', { key: 'h' }, `${t('artifactTitle')} · ${view.runId ?? ''}`),
    view.artifacts.length === 0
      ? createElement('p', { key: 'none', style: { ...muted, margin: 0 } }, t('noArtifacts'))
      : view.artifacts.map(artifact => createElement('article', { key: artifact.id, style: section },
        createElement('strong', null, artifact.title ?? artifact.id),
        createElement('span', { style: muted }, [artifact.type, artifact.status, artifact.createdAt].filter(Boolean).join(' · ') || t('notReported')),
        // Plain text only: report markdown is never interpreted as HTML here.
        artifact.markdown ? createElement('pre', { style: { margin: 0, whiteSpace: 'pre-wrap', fontSize: 12, fontFamily: 'inherit' } }, artifact.markdown) : null,
        artifact.markdownTruncated ? createElement('span', { style: muted }, t('truncated')) : null)),
    createElement('section', { key: 'ev', style: section },
      createElement('strong', null, t('evidence')),
      view.evidenceAvailable === false
        ? createElement('span', { style: warn, 'data-evidence': 'unavailable' }, t('evidenceUnavailable'))
        : view.evidence.length === 0
          ? createElement('span', { style: muted }, t('noEvidence'))
          : createElement('ul', { style: { margin: 0, paddingLeft: 18, display: 'grid', gap: 4, fontSize: 13 } }, view.evidence.map((item, index) => createElement('li', { key: item.id ?? index },
            item.url ? createElement('a', { href: item.url, target: '_blank', rel: 'noopener noreferrer' }, item.title ?? item.url) : (item.title ?? t('notReported')),
            item.source || item.publishedAt ? createElement('span', { style: muted }, ` · ${[item.source, item.publishedAt].filter(Boolean).join(' · ')}`) : null)))),
  ])
}

export function BacktestArtifactBody({ useTabInfo, useResource, t }: BodyProps): ReactElement {
  const { tab } = useTabInfo()
  const snapshot = useResource<'puregamma-backtest-artifact'>(tab.contentId)
  return stateful(snapshot, t, 'puregamma-backtest-artifact', view => {
    const run = view.run!
    return [
      createElement('strong', { key: 'h' }, run.strategyName ?? run.id),
      createElement('div', { key: 'g', style: grid },
        ...field(t('status'), run.status, t),
        ...field(t('engine'), run.engine, t),
        ...field(t('asset'), run.asset, t),
        ...field(t('window'), run.windowStart && run.windowEnd ? `${run.windowStart} → ${run.windowEnd}` : undefined, t),
        ...field(t('created'), run.createdAt, t),
        ...field(t('completed'), run.completedAt, t)),
      run.isLegacy ? createElement('span', { key: 'l', style: muted }, t('legacy')) : null,
      run.errorMessage ? createElement('div', { key: 'e', style: warn, role: 'alert' }, `${t('error')}: ${run.errorMessage}`) : null,
      createElement('section', { key: 'm', style: section },
        createElement('strong', null, t('metrics')),
        view.metrics.length === 0
          ? createElement('span', { style: muted }, t('noMetrics'))
          : createElement('div', { style: { ...grid, fontVariantNumeric: 'tabular-nums' } }, ...view.metrics.flatMap(metric => [
            createElement('div', { key: `${metric.name}:l`, style: muted }, metric.name),
            createElement('div', { key: `${metric.name}:v` }, String(metric.value)),
          ]))),
      createElement('section', { key: 'f', style: section },
        createElement('strong', null, t('files')),
        view.artifacts.length === 0
          ? createElement('span', { style: muted }, t('noArtifacts'))
          : createElement('ul', { style: { margin: 0, paddingLeft: 18, fontSize: 13 } }, view.artifacts.map(file => createElement('li', { key: file.id },
            [file.artifactType, file.format, file.sizeBytes === undefined ? undefined : `${file.sizeBytes} ${t('size')}`, file.checksum ? `${t('checksum')} ${file.checksum.slice(0, 12)}` : undefined, file.createdAt].filter(Boolean).join(' · ') || file.id)))),
      createElement('span', { key: 's', style: muted }, t('simulated')),
    ]
  })
}

function runList<V extends { available: boolean; reason?: string; observedAt: string; source: string } & Freshness>(snapshot: ResourceSnapshot<V>, t: T, testId: string, rows: (value: V) => { id: string; label: string; detail: string; address: string }[], open: (address: string) => void): ReactElement {
  return stateful(snapshot, t, testId, value => {
    const items = rows(value)
    if (items.length === 0) return createElement('span', { style: muted }, t('noRuns'))
    return createElement('ul', { style: { margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 6 } }, items.map(item => createElement('li', { key: item.id, style: { display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' } },
      createElement('button', { type: 'button', style: button, onClick: () => open(item.address), 'aria-label': `${t('open')} ${item.label}` }, item.label),
      createElement('span', { style: muted }, item.detail))))
  })
}

export function IndexBody({ useTabInfo, useResource, t }: BodyProps): ReactElement {
  const { tab } = useTabInfo()
  const research = useResource<'puregamma-research-index'>(INDEX_ADDRESS)
  const backtests = useResource<'puregamma-backtest-index'>(BACKTEST_INDEX_ADDRESS)
  const open = (address: string): void => tab.actions.openResource(address)
  return createElement('div', { style: { ...page, padding: 0, gap: 0 }, 'data-testid': 'puregamma-research-index' },
    createElement('h2', { style: { margin: '16px 16px 0', fontSize: 15 } }, t('researchRuns')),
    runList(research, t, 'puregamma-research-index-runs', value => value.runs.map(run => ({ id: run.id, label: run.name ?? run.id, detail: [run.status ?? t('notReported'), run.updatedAt ?? run.createdAt].filter(Boolean).join(' · '), address: resourceAddress(PROTOCOL.researchRun, run.id) })), open),
    createElement('h2', { style: { margin: '8px 16px 0', fontSize: 15 } }, t('backtestRuns')),
    runList(backtests, t, 'puregamma-backtest-index-runs', value => value.runs.map(run => ({ id: run.id, label: run.strategyName ?? run.id, detail: [run.status ?? t('notReported'), run.asset, run.createdAt].filter(Boolean).join(' · '), address: resourceAddress(PROTOCOL.backtestArtifact, run.id) })), open))
}

const RUN_POLL_MS = 3000
const ARTIFACT_POLL_MS = 15000
const INDEX_POLL_MS = 30000

function tabTitle(protocol: ProtocolName, label: string): (address: string) => string {
  return address => {
    const id = resourceId(address, protocol)
    return id === undefined ? label : `${label} · ${id.length > 12 ? `${id.slice(0, 12)}…` : id}`
  }
}

export const inject = ['slots', 'locale', 'resources', 'remote', 'remote.puregammaClient', 'sidebarRightTabs']

export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-research-resources: dictionaries')
  const t = ctx.locale.bind(NS) as T
  const remote = ctx.remote.puregammaClient
  const unavailable = <V>(reason: string, extra: V) => ({ ok: true as const, value: { available: false, observedAt: new Date().toISOString(), source: PLUGIN, reason, ...extra } })

  ctx.effect(() => ctx.resources.register<'puregamma-research-run'>({
    protocol: PROTOCOL.researchRun,
    async *open(address, { signal }) {
      const id = resourceId(address, PROTOCOL.researchRun)
      if (id === undefined) { yield unavailable('invalid research run address', { connection: 'ended' as const }); return }
      yield* followResearchRun({ researchRun: runId => remote.researchRun(runId), researchRunWait: (runId, status) => remote.researchRunWait(runId, status) }, id, signal, { minIntervalMs: RUN_POLL_MS })
    },
  }), 'puregamma-research-resources: research run provider')
  ctx.effect(() => ctx.resources.register<'puregamma-research-artifact'>({
    protocol: PROTOCOL.researchArtifact,
    async *open(address, { signal }) {
      const id = resourceId(address, PROTOCOL.researchArtifact)
      if (id === undefined) { yield unavailable('invalid research artifact address', { artifacts: [], evidence: [] }); return }
      yield* pollResource(() => remote.researchArtifacts(id), signal, ARTIFACT_POLL_MS)
    },
  }), 'puregamma-research-resources: research artifact provider')
  ctx.effect(() => ctx.resources.register<'puregamma-backtest-artifact'>({
    protocol: PROTOCOL.backtestArtifact,
    async *open(address, { signal }) {
      const id = resourceId(address, PROTOCOL.backtestArtifact)
      if (id === undefined) { yield unavailable('invalid backtest artifact address', { metrics: [], artifacts: [] }); return }
      yield* pollResource(() => remote.backtestArtifact(id), signal, ARTIFACT_POLL_MS)
    },
  }), 'puregamma-research-resources: backtest artifact provider')
  ctx.effect(() => ctx.resources.register<'puregamma-research-index'>({
    protocol: PROTOCOL.researchIndex,
    async *open(_address, { signal }) { yield* pollResource(() => remote.researchRuns(), signal, INDEX_POLL_MS) },
  }), 'puregamma-research-resources: research index provider')
  ctx.effect(() => ctx.resources.register<'puregamma-backtest-index'>({
    protocol: PROTOCOL.backtestIndex,
    async *open(_address, { signal }) { yield* pollResource(() => remote.backtestRuns(), signal, INDEX_POLL_MS) },
  }), 'puregamma-research-resources: backtest index provider')

  const resourceTypes = [
    { id: TAB_IDS.researchRun, protocol: PROTOCOL.researchRun, label: () => t('runTitle'), body: ResearchRunBody },
    { id: TAB_IDS.researchArtifact, protocol: PROTOCOL.researchArtifact, label: () => t('artifactTitle'), body: ResearchArtifactBody },
    { id: TAB_IDS.backtestArtifact, protocol: PROTOCOL.backtestArtifact, label: () => t('backtestTitle'), body: BacktestArtifactBody },
  ] as const
  for (const type of resourceTypes) {
    ctx.effect(() => ctx.sidebarRightTabs.register({
      id: type.id, kind: type.protocol, patterns: [`dsh-resource://${type.protocol}/**`], priority: 'extension',
      canOpen: address => resourceId(address, type.protocol) !== undefined,
      title: address => tabTitle(type.protocol, type.label())(address),
    }), `puregamma-research-resources: ${type.protocol} tab type`)
    ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab', key: type.id, inject: () => ({ t }) }, type.body))
  }
  ctx.effect(() => ctx.sidebarRightTabs.register({
    id: TAB_IDS.index, kind: INDEX_KIND, title: () => t('indexTitle'),
    guide: [{ id: 'recent', order: 60, title: () => t('guide'), description: () => t('guideDescription') }],
  }), 'puregamma-research-resources: index page type')
  ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab', key: TAB_IDS.index, inject: () => ({ t }) }, IndexBody))
}
