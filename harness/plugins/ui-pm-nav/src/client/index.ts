import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { UseResource } from '@deepseek-ai/dsh-client-resources/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@puregamma/dsh-client-remotes/client'
import type {} from '@puregamma/dsh-client-gateway/remote'
import type { PmBag, PureGammaPmAccountView, PureGammaPmNavHistoryView } from '@puregamma/dsh-client-gateway'

const ACCOUNT_ADDRESS = 'dsh-resource://puregamma-pm-nav/account'
const HISTORY_ADDRESS = 'dsh-resource://puregamma-pm-nav/history'
const NS = 'puregamma.pm-nav'
const POLL_MS = 60_000

/** The server's refusal code, mapped to an explicit message instead of a blank panel. */
const NOT_AUTHORIZED = 'PM_ACCOUNT_NOT_AUTHORIZED'

const en = {
  nav: 'Private PM account',
  title: 'Binance Portfolio Margin (private)',
  subtitle: 'Collected read-only by an independent collector. PureGamma holds no API key for this account and cannot place, cancel or transfer anything.',
  loading: 'Loading private account…',
  unavailable: 'Private account unavailable',
  notAuthorized: 'This account is not authorized to view the private portfolio.',
  stale: 'STALE',
  live: 'LIVE',
  ageSeconds: 'age',
  asOf: 'as of',
  equity: 'Adjusted equity',
  equityHint: 'Official exchange figure: market value minus liabilities',
  marginEquity: 'Margin equity',
  marginEquityHint: 'accountEquity / uniMMR basis — stricter, not the account value',
  availableBalance: 'Available balance',
  unrealized: 'Unrealized PnL',
  uniMmr: 'uniMMR',
  initialMargin: 'Initial margin',
  maintMargin: 'Maintenance margin',
  equityBuffer: 'Equity buffer',
  maintUsage: 'Maintenance usage',
  btcHeld: 'BTC held',
  btcPrice: 'BTC price',
  equityBtc: 'Equity in BTC',
  availableBtc: 'Available in BTC',
  grossNotional: 'Gross notional',
  grossNotionalBtc: 'Gross notional (BTC)',
  navCurve: 'NAV (official adjusted equity)',
  navInsufficient: 'Not enough observations to draw a curve yet.',
  navGap: 'Real snapshots only; gaps are not interpolated.',
  positions: 'Positions',
  symbol: 'Symbol',
  side: 'Side',
  quantity: 'Qty',
  mark: 'Mark',
  notional: 'Notional',
  pnl: 'uPnL',
  noPositions: 'No open positions.',
  risk: 'Risk rules firing',
  noRisk: 'No risk rule is firing.',
  coverage: 'Coverage',
  restOk: 'REST',
  wsConnected: 'WebSocket',
  ordersCovered: 'Orders covered',
  failures: 'Failures',
  yes: 'ok',
  no: 'not ok',
  unknown: 'unknown',
  source: 'Source',
  readOnly: 'read-only',
  privateNote: 'This private account is never merged into any user aggregate NAV.',
  notMerged: 'Not merged into portfolio NAV',
} as const
const zh: Record<keyof typeof en, string> = {
  nav: '私有 PM 账户',
  title: '币安统一账户（私有）',
  subtitle: '由独立采集器只读采集。PureGamma 不持有该账户的任何 API Key，不具备下单、撤单或划转能力。',
  loading: '正在读取私有账户…',
  unavailable: '私有账户不可用',
  notAuthorized: '该账户无权查看私有组合。',
  stale: '数据过期',
  live: '实时',
  ageSeconds: '距今',
  asOf: '数据时间',
  equity: '调整后权益',
  equityHint: '交易所官方口径：市值 − 负债',
  marginEquity: '保证金权益',
  marginEquityHint: 'accountEquity / uniMMR 口径，更严格，不代表账户价值',
  availableBalance: '可用余额',
  unrealized: '未实现盈亏',
  uniMmr: '统一维持保证金率',
  initialMargin: '初始保证金',
  maintMargin: '维持保证金',
  equityBuffer: '权益缓冲',
  maintUsage: '维持保证金占用',
  btcHeld: '持有 BTC',
  btcPrice: 'BTC 价格',
  equityBtc: '权益（BTC）',
  availableBtc: '可用（BTC）',
  grossNotional: '总名义价值',
  grossNotionalBtc: '总名义价值（BTC）',
  navCurve: '净值（官方调整后权益）',
  navInsufficient: '快照数量不足，暂不绘制曲线。',
  navGap: '仅真实快照，不做插值。',
  positions: '持仓',
  symbol: '合约',
  side: '方向',
  quantity: '数量',
  mark: '标记价',
  notional: '名义价值',
  pnl: '未实现盈亏',
  noPositions: '当前无持仓。',
  risk: '触发的风控规则',
  noRisk: '当前无风控规则触发。',
  coverage: '覆盖情况',
  restOk: 'REST',
  wsConnected: 'WebSocket',
  ordersCovered: '订单覆盖',
  failures: '失败项',
  yes: '正常',
  no: '异常',
  unknown: '未知',
  source: '数据源',
  readOnly: '只读',
  privateNote: '该私有账户绝不并入任何用户的总净值。',
  notMerged: '不并入组合净值',
}
type Key = keyof typeof en

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface ResourceProtocolMap {
    'puregamma-pm-nav-account': PureGammaPmAccountView
    'puregamma-pm-nav-history': PureGammaPmNavHistoryView
  }
  interface LocaleNamespaceMap { 'puregamma.pm-nav': Key }
}

// ------------------------------------------------------------------ formatting

/** Provider values are Decimal strings; never coerce a non-numeric string to 0. */
function num(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function fmtUsd(value: unknown, digits = 2): string {
  const parsed = num(value)
  if (parsed === null) return '--'
  return `$${parsed.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

function fmtBtc(value: unknown, digits = 6): string {
  const parsed = num(value)
  if (parsed === null) return '--'
  return `${parsed.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: digits })} BTC`
}

function fmtPlain(value: unknown, digits = 2): string {
  const parsed = num(value)
  if (parsed === null) return '--'
  return parsed.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtSignedUsd(value: unknown): string {
  const parsed = num(value)
  if (parsed === null) return '--'
  return `${parsed >= 0 ? '+' : '−'}${fmtUsd(Math.abs(parsed))}`
}

// ---------------------------------------------------------------------- styles

const sectionStyle: CSSProperties = { display: 'grid', gap: 14, maxWidth: 900 }
const cardStyle: CSSProperties = {
  border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', borderRadius: 14,
  background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', padding: 16, display: 'grid', gap: 12,
}
const labelStyle: CSSProperties = { color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', fontSize: 12 }
const dimStyle: CSSProperties = { color: 'var(--dsw-text-secondary, rgba(127,127,127,.75))', fontSize: 11 }
const heroStyle: CSSProperties = { fontSize: 30, fontWeight: 640, fontVariantNumeric: 'tabular-nums' }
const gridStyle: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }
const tableStyle: CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 12, fontVariantNumeric: 'tabular-nums' }
const thStyle: CSSProperties = { ...dimStyle, textAlign: 'left', padding: '4px 8px 4px 0', fontWeight: 500 }
const tdStyle: CSSProperties = { padding: '4px 8px 4px 0', color: 'var(--dsw-text-primary, inherit)' }

function cell(label: string, hint: string | undefined, value: string): ReactElement {
  return createElement('div', { key: label, style: { display: 'grid', gap: 2 } },
    createElement('div', { style: dimStyle }, label),
    createElement('div', { style: { fontSize: 14, fontWeight: 520, fontVariantNumeric: 'tabular-nums' } }, value),
    hint === undefined ? null : createElement('div', { style: dimStyle }, hint),
  )
}

function badge(text: string, tone: 'ok' | 'warn' | 'muted'): ReactElement {
  const color = tone === 'ok' ? 'var(--dsw-status-positive, #16a34a)' : tone === 'warn' ? 'var(--dsw-status-warning, #d97706)' : 'var(--dsw-text-secondary, rgba(127,127,127,.9))'
  return createElement('span', {
    key: text,
    style: { border: `1px solid ${color}`, color, borderRadius: 999, padding: '1px 8px', fontSize: 10, letterSpacing: '.04em', textTransform: 'uppercase' },
  }, text)
}

/**
 * Plot only real observations. Fewer than two usable points renders the
 * "not enough data" note instead of a fabricated line.
 */
function navSparkline(history: PureGammaPmNavHistoryView): ReactElement | null {
  const points = history.points
    .map(point => ({ t: point.t, v: num(point.adjustedEquityUsd) }))
    .filter((point): point is { t: number; v: number } => point.v !== null)
  if (points.length < 2) return null
  const values = points.map(point => point.v)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = 100 / (points.length - 1)
  const path = points.map((point, index) => `${(index * step).toFixed(2)},${(28 - ((point.v - min) / span) * 26).toFixed(2)}`).join(' ')
  return createElement('svg', {
    viewBox: '0 0 100 30', preserveAspectRatio: 'none', width: '100%', height: 90,
    role: 'img', 'aria-label': 'NAV history',
  }, createElement('polyline', { points: path, fill: 'none', stroke: 'var(--dsw-accent, #4f7cff)', strokeWidth: 0.8, vectorEffect: 'non-scaling-stroke' }))
}

function positionsTable(t: (key: Key) => string, positions: readonly PmBag[] | undefined): ReactElement {
  if (positions === undefined || positions.length === 0) return createElement('p', { style: labelStyle }, t('noPositions'))
  return createElement('table', { style: tableStyle },
    createElement('thead', null, createElement('tr', null,
      ...(['symbol', 'side', 'quantity', 'mark', 'notional', 'pnl'] as const).map(key => createElement('th', { key, style: thStyle }, t(key))),
    )),
    createElement('tbody', null, ...positions.map((row, index) => createElement('tr', { key: `${String(row.symbol ?? index)}-${index}` },
      createElement('td', { style: tdStyle }, String(row.symbol ?? '--')),
      createElement('td', { style: tdStyle }, String(row.side ?? '--')),
      createElement('td', { style: tdStyle }, fmtPlain(row.quantity, 6)),
      createElement('td', { style: tdStyle }, fmtUsd(row.mark_price, 4)),
      createElement('td', { style: tdStyle }, fmtUsd(row.notional_usd)),
      createElement('td', { style: tdStyle }, fmtSignedUsd(row.unrealized_pnl)),
    ))),
  )
}

// -------------------------------------------------------------------- resource

function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise(resolve => {
    const done = (): void => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
    const timer = setTimeout(done, ms)
    signal.addEventListener('abort', done, { once: true })
  })
}

function PmNavSection({ useResource, t }: { useResource: UseResource; t: (key: Key) => string }): ReactElement {
  const account = useResource<'puregamma-pm-nav-account'>(ACCOUNT_ADDRESS)
  const history = useResource<'puregamma-pm-nav-history'>(HISTORY_ADDRESS)
  if (account.status === 'loading' || account.status === 'none') {
    return createElement('section', { style: sectionStyle }, createElement('p', { style: labelStyle }, t('loading')))
  }
  if (account.status === 'failed' || account.value === undefined) {
    return createElement('section', { style: sectionStyle },
      createElement('div', { style: cardStyle }, createElement('strong', null, t('unavailable'))))
  }
  const view = account.value
  if (!view.available) {
    const reason = view.reason === NOT_AUTHORIZED ? t('notAuthorized') : (view.reason ?? t('unavailable'))
    return createElement('section', { style: sectionStyle },
      createElement('header', null,
        createElement('h2', { style: { margin: 0, fontSize: 18, fontWeight: 620 } }, t('title')),
        createElement('p', { style: { ...labelStyle, margin: '6px 0 0' } }, t('subtitle')),
      ),
      createElement('div', { style: cardStyle },
        createElement('strong', null, t('unavailable')),
        createElement('span', { style: labelStyle }, reason),
      ),
    )
  }

  // The curve is drawn only from a history payload the server reports as
  // available; a failed history read never becomes an empty flat line.
  const nav = history.value !== undefined && history.value.available ? history.value : null
  const accountBag = view.account ?? {}
  const btcBag = view.btc ?? {}
  const exposureBag = view.exposure ?? {}
  const positions = view.positions ?? []
  const firing = view.risk?.firing ?? []
  const ageText = view.ageSeconds === undefined || view.ageSeconds === null ? t('unknown') : `${fmtPlain(view.ageSeconds, 0)}s`
  const quality = view.quality

  return createElement('section', { style: sectionStyle },
    createElement('header', null,
      createElement('div', { style: { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' } },
        createElement('h2', { style: { margin: 0, fontSize: 18, fontWeight: 620 } }, t('title')),
        view.stale === true ? badge(t('stale'), 'warn') : badge(t('live'), 'ok'),
        badge(t('readOnly'), 'muted'),
        badge(t('notMerged'), 'muted'),
      ),
      createElement('p', { style: { ...labelStyle, margin: '6px 0 0' } }, t('subtitle')),
    ),

    createElement('div', { style: cardStyle },
      createElement('div', null,
        createElement('div', { style: labelStyle }, t('equity')),
        createElement('div', { style: heroStyle }, fmtUsd(accountBag.adjusted_equity_usd)),
        createElement('div', { style: dimStyle }, t('equityHint')),
      ),
      createElement('div', { style: gridStyle },
        cell(t('marginEquity'), t('marginEquityHint'), fmtUsd(accountBag.account_equity_usd)),
        cell(t('availableBalance'), undefined, fmtUsd(accountBag.total_available_balance_usd)),
        cell(t('unrealized'), undefined, fmtSignedUsd(accountBag.total_unrealized_pnl_usd)),
        cell(t('uniMmr'), undefined, fmtPlain(accountBag.uni_mmr, 4)),
        cell(t('initialMargin'), undefined, fmtUsd(accountBag.account_initial_margin_usd)),
        cell(t('maintMargin'), undefined, fmtUsd(accountBag.account_maint_margin_usd)),
        cell(t('equityBuffer'), undefined, fmtUsd(accountBag.equity_buffer_derived)),
        cell(t('maintUsage'), undefined, fmtPlain(accountBag.maint_margin_usage_derived, 4)),
      ),
      createElement('div', { style: gridStyle },
        cell(t('btcHeld'), undefined, fmtBtc(btcBag.quantity, 8)),
        cell(t('btcPrice'), undefined, fmtUsd(btcBag.price_usd)),
        cell(t('equityBtc'), undefined, fmtBtc(accountBag.equity_btc_equivalent, 8)),
        cell(t('availableBtc'), undefined, fmtBtc(accountBag.available_btc_equivalent, 8)),
        cell(t('grossNotional'), undefined, fmtUsd(exposureBag.gross_notional_usd)),
        cell(t('grossNotionalBtc'), undefined, fmtBtc(exposureBag.gross_notional_btc_equivalent, 8)),
      ),
      createElement('div', { style: { ...dimStyle, display: 'flex', gap: 14, flexWrap: 'wrap' } },
        createElement('span', null, `${t('asOf')}: ${view.dataAsOf ?? t('unknown')}`),
        createElement('span', null, `${t('ageSeconds')}: ${ageText}`),
        createElement('span', null, `${t('source')}: ${view.venue ?? t('unknown')} (${t('readOnly')})`),
      ),
      createElement('p', { style: dimStyle }, view.sourceNote ?? ''),
    ),

    createElement('div', { style: cardStyle },
      createElement('div', { style: labelStyle }, t('navCurve')),
      nav === null || nav.sufficient !== true
        ? createElement('p', { style: labelStyle }, t('navInsufficient'))
        : navSparkline(nav),
      createElement('div', { style: dimStyle }, `${t('navGap')} ${nav?.pointCount ?? 0} points`),
    ),

    createElement('div', { style: cardStyle },
      createElement('div', { style: labelStyle }, t('positions')),
      positionsTable(t, positions),
    ),

    createElement('div', { style: cardStyle },
      createElement('div', { style: labelStyle }, t('risk')),
      firing.length === 0
        ? createElement('p', { style: labelStyle }, t('noRisk'))
        : createElement('ul', { style: { margin: 0, paddingLeft: 18, fontSize: 12 } },
            ...firing.map((row, index) => createElement('li', { key: `${String(row.rule ?? index)}-${index}` },
              `${String(row.rule ?? '--')} [${String(row.level ?? '--')}] ${row.value === null || row.value === undefined ? '' : String(row.value)}`))),
    ),

    createElement('div', { style: cardStyle },
      createElement('div', { style: labelStyle }, t('coverage')),
      createElement('div', { style: { ...dimStyle, display: 'flex', gap: 14, flexWrap: 'wrap' } },
        createElement('span', null, `${t('restOk')}: ${quality?.restOk === true ? t('yes') : quality?.restOk === false ? t('no') : t('unknown')}`),
        createElement('span', null, `${t('wsConnected')}: ${quality?.wsConnected === true ? t('yes') : quality?.wsConnected === false ? t('no') : t('unknown')}`),
        createElement('span', null, `${t('ordersCovered')}: ${view.coverage?.ordersCovered === true ? t('yes') : view.coverage?.ordersCovered === false ? t('no') : t('unknown')}`),
        createElement('span', null, `${t('failures')}: ${(view.coverage?.failures?.length ?? 0) + (view.coverage?.essentialFailures?.length ?? 0)}`),
      ),
      quality?.lastError === null || quality?.lastError === undefined ? null : createElement('div', { style: dimStyle }, quality.lastError),
      createElement('p', { style: dimStyle }, t('privateNote')),
      view.disclaimer === undefined ? null : createElement('p', { style: dimStyle }, view.disclaimer),
    ),
  )
}

export const inject = ['slots', 'locale', 'resources', 'remote', 'remote.puregammaClient']

export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-pm-nav: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  ctx.effect(() => ctx.resources.register<'puregamma-pm-nav-account'>({
    protocol: 'puregamma-pm-nav-account',
    async *open(_address, { signal }) {
      while (!signal.aborted) {
        yield await ctx.remote.puregammaClient.pmAccount()
        await wait(POLL_MS, signal)
      }
    },
  }), 'puregamma-pm-nav: account resource')
  ctx.effect(() => ctx.resources.register<'puregamma-pm-nav-history'>({
    protocol: 'puregamma-pm-nav-history',
    async *open(_address, { signal }) {
      while (!signal.aborted) {
        yield await ctx.remote.puregammaClient.pmNavHistory()
        await wait(POLL_MS, signal)
      }
    },
  }), 'puregamma-pm-nav: history resource')
  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section', id: 'puregamma-pm-nav', order: 50, label: () => t('nav'), inject: () => ({ t }),
  }, PmNavSection))
}
