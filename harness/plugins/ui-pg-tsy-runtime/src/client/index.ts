import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { UseResource } from '@deepseek-ai/dsh-client-resources/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@puregamma/dsh-client-remotes/client'
import type {} from '@puregamma/dsh-client-gateway/remote'
import type { PureGammaQuantRuntimeView } from '@puregamma/dsh-client-gateway'

const ADDRESS = 'dsh-resource://puregamma-pg-tsy-runtime/current'
const NS = 'puregamma.pg-tsy-runtime'
const POLL_MS = 15_000

const en = {
  nav: 'Quant runtime', title: 'PG-TSY runtime', subtitle: 'Read-only health from the installed PG-TSY Cordis service; this panel cannot submit orders or enable live trading.',
  loading: 'Loading runtime health…', unavailable: 'Runtime health unavailable', source: 'Source', observed: 'Observed',
  process: 'Process', readiness: 'Readiness', mode: 'Mode', lease: 'Lease / fencing', feeds: 'Feeds connected',
  events: 'Events', decisions: 'Policy decisions', orders: 'Open orders', journaled: 'Orders journaled',
  gates: 'Blocking safety gates', noGates: 'No blocking gates reported', error: 'Last error',
  healthy: 'Healthy', unhealthy: 'Unhealthy', ready: 'Ready', notReady: 'Not ready', unknown: 'Unknown', missing: '—',
  noEvidence: 'Not reported — this does not establish live-trading safety.',
} as const
const zh: Record<keyof typeof en, string> = {
  nav: '量化运行时', title: 'PG-TSY 运行状态', subtitle: '来自已安装 PG-TSY Cordis Service 的只读状态。本面板无法下单或启用实盘。',
  loading: '正在读取运行状态…', unavailable: '运行状态暂不可用', source: '数据来源', observed: '观测时间',
  process: '进程健康', readiness: '就绪状态', mode: '运行模式', lease: 'Lease / Fencing', feeds: '已连接行情源',
  events: '事件总数', decisions: '风控策略决策', orders: '未结订单', journaled: '已记账订单',
  gates: '阻断安全门禁', noGates: '未报告阻断门禁', error: '最近错误',
  healthy: '健康', unhealthy: '异常', ready: '已就绪', notReady: '未就绪', unknown: '未知', missing: '—',
  noEvidence: '未报告安全证据；不能据此认定实盘安全。',
}
type Key = keyof typeof en

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface ResourceProtocolMap { 'puregamma-pg-tsy-runtime': PureGammaQuantRuntimeView }
  interface LocaleNamespaceMap { 'puregamma.pg-tsy-runtime': Key }
}

const panelStyle: CSSProperties = { display: 'grid', gap: 14, maxWidth: 860 }
const cardStyle: CSSProperties = { display: 'grid', gap: 12, padding: 16, borderRadius: 14, border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))' }
const gridStyle: CSSProperties = { display: 'grid', gridTemplateColumns: 'minmax(145px, 1fr) minmax(120px, 1.6fr)', gap: '10px 16px' }
const labelStyle: CSSProperties = { fontSize: 12, color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))' }
const valueStyle: CSSProperties = { fontSize: 13, color: 'var(--dsw-text-primary, inherit)', overflowWrap: 'anywhere' }

function row(label: string, value: string | number | undefined, missing: string): ReactElement[] {
  return [createElement('div', { key: `${label}:label`, style: labelStyle }, label), createElement('div', { key: `${label}:value`, style: valueStyle }, value === undefined || value === '' ? missing : String(value))]
}
function flag(value: boolean | undefined, t: (key: Key) => string, ready = false): string {
  if (value === undefined) return t('unknown')
  return value ? t(ready ? 'ready' : 'healthy') : t(ready ? 'notReady' : 'unhealthy')
}
function RuntimeSection({ useResource, t }: { useResource: UseResource; t: (key: Key) => string }): ReactElement {
  const snapshot = useResource<'puregamma-pg-tsy-runtime'>(ADDRESS)
  if (snapshot.status === 'loading' || snapshot.status === 'none') return createElement('section', { style: panelStyle }, createElement('p', { style: labelStyle }, t('loading')))
  if (snapshot.status === 'failed' || snapshot.value === undefined || !snapshot.value.available) {
    return createElement('section', { style: panelStyle }, createElement('div', { style: cardStyle },
      createElement('strong', null, t('unavailable')),
      snapshot.value?.reason ? createElement('p', { style: labelStyle }, snapshot.value.reason) : null,
      createElement('p', { style: labelStyle }, t('noEvidence'))))
  }
  const runtime = snapshot.value
  const gates = runtime.blockingGates
  return createElement('section', { style: panelStyle },
    createElement('header', null,
      createElement('h2', { style: { fontSize: 18, margin: 0 } }, t('title')),
      createElement('p', { style: { ...labelStyle, margin: '6px 0 0' } }, t('subtitle')),
    ),
    createElement('div', { style: cardStyle }, createElement('div', { style: gridStyle },
      ...row(t('process'), flag(runtime.processHealthy, t), t('missing')),
      ...row(t('readiness'), flag(runtime.ready, t, true), t('missing')),
      ...row(t('mode'), runtime.mode, t('missing')),
      ...row(t('lease'), flag(runtime.leaseHealthy, t), t('missing')),
      ...row(t('feeds'), runtime.feedsConnected === undefined || runtime.feedsTotal === undefined ? undefined : `${runtime.feedsConnected} / ${runtime.feedsTotal}`, t('missing')),
      ...row(t('events'), runtime.eventsTotal, t('missing')),
      ...row(t('decisions'), runtime.policyDecisionsTotal, t('missing')),
      ...row(t('orders'), runtime.openOrders, t('missing')),
      ...row(t('journaled'), runtime.ordersJournaledTotal, t('missing')),
    )),
    createElement('div', { style: cardStyle },
      createElement('strong', { style: valueStyle }, t('gates')),
      gates === undefined ? createElement('p', { style: labelStyle }, t('noEvidence'))
        : gates.length === 0 ? createElement('p', { style: labelStyle }, t('noGates'))
          : createElement('ul', { style: { margin: 0, paddingLeft: 22, overflowWrap: 'anywhere' } }, ...gates.map((gate, index) => createElement('li', { key: `${gate}-${index}`, style: valueStyle }, gate))),
      runtime.lastError ? createElement('p', { style: valueStyle }, `${t('error')}: ${runtime.lastError}`) : null,
    ),
    createElement('footer', { style: { ...labelStyle, display: 'flex', gap: 12, flexWrap: 'wrap' } },
      createElement('span', null, `${t('source')}: ${runtime.source}`),
      createElement('span', null, `${t('observed')}: ${runtime.observedAt}`),
    ),
  )
}
function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise(resolve => {
    const done = (): void => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
    const timer = setTimeout(done, ms)
    signal.addEventListener('abort', done, { once: true })
  })
}
export const inject = ['slots', 'locale', 'resources', 'remote', 'remote.puregammaClient']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-pg-tsy-runtime: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  ctx.effect(() => ctx.resources.register<'puregamma-pg-tsy-runtime'>({
    protocol: 'puregamma-pg-tsy-runtime',
    async *open(_address, { signal }) {
      while (!signal.aborted) {
        yield await ctx.remote.puregammaClient.quantRuntime()
        await wait(POLL_MS, signal)
      }
    },
  }), 'puregamma-pg-tsy-runtime: resource provider')
  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section', id: 'puregamma-pg-tsy-runtime', order: 45, label: () => t('nav'), inject: () => ({ t }),
  }, RuntimeSection))
}
