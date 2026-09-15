import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { UseResource } from '@deepseek-ai/dsh-client-resources/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@puregamma/dsh-client-remotes/client'
import type {} from '@puregamma/dsh-client-gateway/remote'
import type {
  PureGammaBillingBudget,
  PureGammaBillingReward,
  PureGammaBillingUsage,
  PureGammaBillingView,
} from '@puregamma/dsh-client-gateway'

const ADDRESS = 'dsh-resource://puregamma-billing/current'
const NS = 'puregamma.billing'
const POLL_MS = 30_000

type Plan = { name: string; price: string; credits: string; tagline: string; benefits: string[] }

const en = {
  nav: 'Billing', title: 'Access & Subscription', subtitle: 'Subscription state, Credits, automation budgets and usage from the billing capability.',
  loading: 'Loading billing…', unavailable: 'Billing unavailable', currentPlan: 'Current plan', subscription: 'Subscription', credits: 'Credits', periodEnd: 'Period end',
  checkoutMode: 'Checkout mode', paymentLink: 'Primary Payment Link', configured: 'Configured', notConfigured: 'Not configured',
  budgets: 'Automation credit budgets', hardStop: 'Hard stop when exhausted', automation: 'Automation', thisMonth: 'This month', nextEstimate: 'Next estimate', status: 'Status',
  paused: 'Paused', active: 'Active', disabled: 'Disabled', noBudgets: 'No automation budgets yet', rewards: 'Reward history', noRewards: 'No rewards yet',
  usage: 'Usage history', noUsage: 'No credit activity yet', action: 'Action', delta: 'Delta', balanceAfter: 'Balance after', created: 'Created', entitlements: 'Entitlements',
  notificationChannels: 'Notification channels', highCostTasks: 'High-cost research', imessage: 'iMessage', enabled: 'Enabled', unavailableValue: 'Unavailable',
  source: 'Source', observed: 'Observed', creditsPerMonth: 'credits / month', perMonth: ' / month', activeBadge: 'Active',
  freeTagline: 'Build a basic market review habit.', free1: 'Core asset watchlist', free2: '1 portfolio connection', free3: 'Shared market brief', free4: 'Basic event view', free5: 'Email delivery',
  proTagline: 'For active investors following a personal portfolio.', pro1: '20–50 assets', pro2: 'Daily portfolio brief', pro3: 'Important event alerts', pro4: 'Limited deep research', pro5: 'Telegram / Email', pro6: 'Basic backtesting',
  maxTagline: 'For multi-portfolio and high-frequency research workflows.', max1: 'Everything in Pro', max2: 'Multiple portfolios', max3: 'Higher Agent allowance', max4: 'iMessage', max5: 'High-frequency monitoring', max6: 'Advanced backtesting', max7: 'Private Playbooks',
  enterpriseTagline: 'For teams, custom data, and private deployment.', enterprise1: 'Team workspace', enterprise2: 'API access', enterprise3: 'Custom data sources', enterprise4: 'Private deployment', enterprise5: 'Dedicated support and compliance configuration',
} as const

const zh: Record<keyof typeof en, string> = {
  nav: '计费', title: '访问权限与订阅', subtitle: '来自 Billing capability 的订阅、Credits、自动化预算与使用状态。', loading: '正在读取计费…', unavailable: '计费暂不可用', currentPlan: '当前套餐', subscription: '订阅', credits: 'Credits', periodEnd: '周期结束',
  checkoutMode: 'Checkout 模式', paymentLink: 'Primary Payment Link', configured: '已配置', notConfigured: '未配置', budgets: '自动化 Credits 预算', hardStop: '不足时自动暂停', automation: '自动化', thisMonth: '本月', nextEstimate: '下次预计', status: '状态',
  paused: '已暂停', active: '运行中', disabled: '已关闭', noBudgets: '暂无自动化预算', rewards: '奖励记录', noRewards: '暂无奖励', usage: '使用记录', noUsage: '暂无 Credit 使用记录', action: '操作', delta: '变化', balanceAfter: '变动后余额', created: '创建时间', entitlements: '权益',
  notificationChannels: '通知渠道', highCostTasks: '高成本研究', imessage: 'iMessage', enabled: '已启用', unavailableValue: '不可用', source: '数据源', observed: '观测时间', creditsPerMonth: 'Credits / 月', perMonth: ' / 月', activeBadge: '当前',
  freeTagline: '建立基础市场观察习惯。', free1: '核心资产观察', free2: '1 个组合账户连接', free3: '共享市场简报', free4: '基础事件视图', free5: 'Email 投递', proTagline: '适合持续跟踪个人组合的主动投资者。', pro1: '20–50 项资产', pro2: '每日组合简报', pro3: '重要事件提醒', pro4: '限量深度研究', pro5: 'Telegram / Email', pro6: '基础回测',
  maxTagline: '适合多组合与高频研究工作流。', max1: '包含全部 Pro 权益', max2: '多组合', max3: '更高 Agent 额度', max4: 'iMessage', max5: '高频监控', max6: '高级回测', max7: '私有 Playbook', enterpriseTagline: '适合团队、定制数据与私有部署。', enterprise1: '团队工作区', enterprise2: 'API 访问', enterprise3: '自定义数据源', enterprise4: '私有部署', enterprise5: '专属支持与合规配置',
}

type Key = keyof typeof en

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface ResourceProtocolMap { 'puregamma-billing': PureGammaBillingView }
  interface LocaleNamespaceMap { 'puregamma.billing': Key }
}

interface BillingSectionProps { useResource: UseResource; t: (key: Key) => string }
const sectionStyle: CSSProperties = { display: 'grid', gap: 14, maxWidth: 980 }
const gridStyle: CSSProperties = { display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }
const cardStyle: CSSProperties = { border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', borderRadius: 14, background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', padding: 16, display: 'grid', gap: 12 }
const labelStyle: CSSProperties = { color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', fontSize: 12 }
const valueStyle: CSSProperties = { color: 'var(--dsw-text-primary, inherit)', fontSize: 14 }
const badgeStyle: CSSProperties = { border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', borderRadius: 999, padding: '3px 8px', fontSize: 11, width: 'fit-content' }

function row(label: string, value: string | number | undefined, missing: string): ReactElement[] {
  return [createElement('div', { key: `${label}-label`, style: labelStyle }, label), createElement('div', { key: `${label}-value`, style: valueStyle }, value === undefined || value === '' ? missing : String(value))]
}

function plans(t: (key: Key) => string): Plan[] {
  const raw: Plan[] = [
    { name: 'Free', price: '$0', credits: '150', tagline: 'Build a basic market review habit.', benefits: ['Core asset watchlist', '1 portfolio connection', 'Shared market brief', 'Basic event view', 'Email delivery'] },
    { name: 'Pro', price: '$29.9', credits: '3,000', tagline: 'For active investors following a personal portfolio.', benefits: ['20–50 assets', 'Daily portfolio brief', 'Important event alerts', 'Limited deep research', 'Telegram / Email', 'Basic backtesting'] },
    { name: 'Max', price: '$199', credits: '15,000', tagline: 'For multi-portfolio and high-frequency research workflows.', benefits: ['Everything in Pro', 'Multiple portfolios', 'Higher Agent allowance', 'iMessage', 'High-frequency monitoring', 'Advanced backtesting', 'Private Playbooks'] },
    { name: 'Enterprise', price: 'Custom', credits: 'Custom', tagline: 'For teams, custom data, and private deployment.', benefits: ['Team workspace', 'API access', 'Custom data sources', 'Private deployment', 'Dedicated support and compliance configuration'] },
  ]
  const taglines: Record<string, Key> = { Free: 'freeTagline', Pro: 'proTagline', Max: 'maxTagline', Enterprise: 'enterpriseTagline' }
  const benefits: Record<string, Partial<Record<string, Key>>> = {
    Free: { 'Core asset watchlist': 'free1', '1 portfolio connection': 'free2', 'Shared market brief': 'free3', 'Basic event view': 'free4', 'Email delivery': 'free5' },
    Pro: { '20–50 assets': 'pro1', 'Daily portfolio brief': 'pro2', 'Important event alerts': 'pro3', 'Limited deep research': 'pro4', 'Telegram / Email': 'pro5', 'Basic backtesting': 'pro6' },
    Max: { 'Everything in Pro': 'max1', 'Multiple portfolios': 'max2', 'Higher Agent allowance': 'max3', 'iMessage': 'max4', 'High-frequency monitoring': 'max5', 'Advanced backtesting': 'max6', 'Private Playbooks': 'max7' },
    Enterprise: { 'Team workspace': 'enterprise1', 'API access': 'enterprise2', 'Custom data sources': 'enterprise3', 'Private deployment': 'enterprise4', 'Dedicated support and compliance configuration': 'enterprise5' },
  }
  return raw.map((plan) => ({ ...plan, tagline: t(taglines[plan.name]), benefits: plan.benefits.map((benefit) => { const key = benefits[plan.name]?.[benefit]; return key === undefined ? benefit : t(key) }) }))
}

function statusBadge(value: boolean | undefined, t: (key: Key) => string): ReactElement {
  return createElement('span', { style: badgeStyle }, value === true ? t('enabled') : t('disabled'))
}

function budgetTable(budgets: PureGammaBillingBudget[], t: (key: Key) => string): ReactElement {
  const headers = [t('automation'), t('thisMonth'), t('nextEstimate'), t('status')]
  const rows = budgets.map((item) => createElement('tr', { key: item.automationKey },
    createElement('td', { style: { padding: 8 } }, item.automationKey),
    createElement('td', { style: { padding: 8 } }, `${item.monthlyUsed ?? 0} / ${item.monthlyLimit ?? '—'}`),
    createElement('td', { style: { padding: 8 } }, item.nextEstimatedCredits === undefined ? '—' : `${item.nextEstimatedCredits} Credits`),
    createElement('td', { style: { padding: 8 } }, item.paused ? t('paused') : item.enabled ? t('active') : t('disabled')),
  ))
  return createElement('div', { style: { overflowX: 'auto' } },
    createElement('table', { style: { width: '100%', minWidth: 650, borderCollapse: 'collapse', fontSize: 12 } },
      createElement('thead', null, createElement('tr', null, ...headers.map((head) => createElement('th', { key: head, style: { textAlign: 'left', padding: '7px 8px', borderBottom: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.18))' } }, head))),
      createElement('tbody', null, ...rows),
    ),
  )
}

function rewardsList(rewards: PureGammaBillingReward[], t: (key: Key) => string): ReactElement {
  if (!rewards.length) return createElement('p', { style: labelStyle }, t('noRewards'))
  return createElement('div', { style: { display: 'grid', gap: 7 } }, ...rewards.slice(0, 8).map((item) => createElement('div', { key: item.id, style: { display: 'flex', justifyContent: 'space-between', gap: 10, borderTop: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.16))', paddingTop: 7, fontSize: 12 } },
    createElement('span', null, item.rewardType ?? 'Reward', createElement('span', { style: labelStyle }, item.createdAt ? ` · ${item.createdAt}` : '')),
    createElement('strong', null, item.credits === undefined ? '—' : `+${item.credits}`),
  )))
}

function usageTable(usage: PureGammaBillingUsage[], t: (key: Key) => string): ReactElement {
  if (!usage.length) return createElement('p', { style: labelStyle }, t('noUsage'))
  const headers = [t('action'), t('delta'), t('balanceAfter'), t('created')]
  const rows = usage.slice(0, 40).map((item, index) => createElement('tr', { key: item.id ?? `${item.createdAt ?? 'usage'}-${index}` },
    createElement('td', { style: { padding: '7px 6px' } }, item.action ?? '—'),
    createElement('td', { style: { padding: '7px 6px' } }, item.creditsDelta ?? '—'),
    createElement('td', { style: { padding: '7px 6px' } }, item.balanceAfter ?? '—'),
    createElement('td', { style: { padding: '7px 6px' } }, item.createdAt ?? '—'),
  ))
  return createElement('div', { style: { maxHeight: 320, overflowY: 'auto' } }, createElement('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: 12 } },
    createElement('thead', null, createElement('tr', null, ...headers.map((head) => createElement('th', { key: head, style: { textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.18))' } }, head))),
    createElement('tbody', null, ...rows),
  ))
}

function BillingSection({ useResource, t }: BillingSectionProps): ReactElement {
  const snapshot = useResource<'puregamma-billing'>(ADDRESS)
  if (snapshot.status === 'loading' || snapshot.status === 'none') return createElement('section', { style: sectionStyle }, createElement('p', { style: labelStyle }, t('loading')))
  if (snapshot.status === 'failed' || snapshot.value === undefined || !snapshot.value.available) {
    const reason = snapshot.value?.reason
    return createElement('section', { style: sectionStyle }, createElement('div', { style: cardStyle }, createElement('strong', null, t('unavailable')), reason ? createElement('span', { style: labelStyle }, reason) : null))
  }
  const billing = snapshot.value
  const currentPlan = billing.plan ?? billing.effectivePlan ?? billing.subscribedPlan
  const entitlement = billing.entitlement
  const planCards = plans(t).map((plan) => createElement('article', { key: plan.name, style: { ...cardStyle, minHeight: 250 } },
    createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start' } },
      createElement('div', null, createElement('strong', { style: { fontSize: 16 } }, plan.name), createElement('div', { style: { marginTop: 6, fontSize: 22, fontWeight: 650 } }, plan.price, createElement('span', { style: { fontSize: 11, fontWeight: 400, ...labelStyle } }, t('perMonth')))),
      currentPlan === plan.name ? createElement('span', { style: badgeStyle }, t('activeBadge')) : null,
    ),
    createElement('div', { style: labelStyle }, `${plan.credits} ${t('creditsPerMonth')}`),
    createElement('p', { style: { ...labelStyle, lineHeight: 1.5, margin: 0 } }, plan.tagline),
    createElement('ul', { style: { margin: 0, paddingLeft: 18, display: 'grid', gap: 6, fontSize: 12 } }, ...plan.benefits.map((benefit) => createElement('li', { key: benefit }, benefit))),
  ))
  return createElement('section', { style: sectionStyle },
    createElement('header', null, createElement('h2', { style: { margin: 0, fontSize: 18, fontWeight: 620 } }, t('title')), createElement('p', { style: { ...labelStyle, margin: '6px 0 0' } }, t('subtitle'))),
    createElement('div', { style: gridStyle }, ...[row(t('currentPlan'), currentPlan, t('unavailableValue')), row(t('subscription'), billing.subscriptionStatus, t('unavailableValue')), row(t('credits'), billing.creditBalance, t('unavailableValue')), row(t('periodEnd'), billing.currentPeriodEnd, t('unavailableValue')), row(t('checkoutMode'), billing.checkoutMode, t('unavailableValue')), row(t('paymentLink'), billing.primaryPaymentLinkConfigured === undefined ? undefined : billing.primaryPaymentLinkConfigured ? t('configured') : t('notConfigured'), t('unavailableValue'))].flat()),
    createElement('div', { style: cardStyle }, createElement('strong', null, t('entitlements')), createElement('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 8 } },
      createElement('span', { style: badgeStyle }, `${t('notificationChannels')}: ${(entitlement?.notificationChannels ?? []).join(', ') || t('unavailableValue')}`),
      createElement('span', { style: badgeStyle }, `${t('highCostTasks')}: `, statusBadge(entitlement?.highCostTasks, t)),
      createElement('span', { style: badgeStyle }, `${t('imessage')}: `, statusBadge(entitlement?.imessage, t)),
    )),
    createElement('div', { style: { ...gridStyle, gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' } }, ...planCards),
    createElement('div', { style: cardStyle }, createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' } }, createElement('strong', null, t('budgets')), createElement('span', { style: badgeStyle }, t('hardStop'))), billing.budgets.length ? budgetTable(billing.budgets, t) : createElement('p', { style: labelStyle }, t('noBudgets'))),
    createElement('div', { style: gridStyle }, createElement('div', { style: cardStyle }, createElement('strong', null, t('rewards')), rewardsList(billing.rewards, t)), createElement('div', { style: cardStyle }, createElement('strong', null, t('usage')), usageTable(billing.usageHistory, t))),
    createElement('div', { style: { ...labelStyle, display: 'flex', gap: 12, flexWrap: 'wrap' } }, createElement('span', null, `${t('source')}: ${billing.source}`), createElement('span', null, `${t('observed')}: ${billing.observedAt}`)),
  )
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise((resolve) => {
    const done = (): void => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
    const timer = setTimeout(done, ms)
    signal.addEventListener('abort', done, { once: true })
  })
}

export const inject = ['slots', 'locale', 'resources', 'remote', 'remote.puregammaClient']

export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-billing: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  ctx.effect(() => ctx.resources.register<'puregamma-billing'>({
    protocol: 'puregamma-billing',
    async *open(_address, { signal }) {
      while (!signal.aborted) {
        yield await ctx.remote.puregammaClient.billing()
        await wait(POLL_MS, signal)
      }
    },
  }), 'puregamma-billing: resource provider')
  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section', id: 'puregamma-billing', order: 30, label: () => t('nav'), inject: () => ({ t }),
  }, BillingSection))
}
