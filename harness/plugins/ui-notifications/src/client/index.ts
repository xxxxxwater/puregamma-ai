import { createElement, useEffect, useState } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { RemoteResult, TypertRemoteNamespace } from '@deepseek-ai/dsh-typert-protocol'
import type { UseResource } from '@deepseek-ai/dsh-client-resources/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@puregamma/dsh-client-remotes/client'
import type {} from '@puregamma/dsh-client-gateway/remote'
import type { PureGammaDailyBriefUpdate, PureGammaNotificationActionResult, PureGammaNotificationsView } from '@puregamma/dsh-client-gateway'

const ADDRESS = 'dsh-resource://puregamma-notifications/current'
const NS = 'puregamma.notifications'
const POLL_MS = 30_000

type Key = keyof typeof en
type NotificationsRemote = TypertRemoteNamespace<'puregammaClient'>

type FormState = {
  enabled: boolean
  timezone: string
  localTime: string
  channel: string
  channels: string
  reportTypes: string
  locale: string
  includePortfolio: boolean
  includeMarket: boolean
  includeSignals: boolean
  includeRisk: boolean
  includeSentiment: boolean
  maxLength: string
}

const en = {
  nav: 'Notifications', title: 'Daily Push & Notifications', subtitle: 'Delivery preferences, report content, iMessage verification and delivery history.', loading: 'Loading notifications…', unavailable: 'Notifications unavailable',
  enabled: 'Enabled', disabled: 'Disabled', timezone: 'Timezone', localTime: 'Local time', channel: 'Primary channel', channels: 'Channels', reportTypes: 'Report types', locale: 'Locale',
  content: 'Report content', portfolio: 'Portfolio', market: 'Market', signals: 'Signals', risk: 'Risk', sentiment: 'Sentiment', maxLength: 'Maximum report length', save: 'Save preferences', saving: 'Saving…',
  tests: 'Test delivery', emailTest: 'Test Email', imessageTest: 'Test iMessage', working: 'Working…', done: 'Action completed.', failed: 'Action unavailable',
  imessage: 'iMessage', officialNumber: 'Official number', provider: 'Provider', enabledPlans: 'Enabled plans', recipient: 'Recipient', verifiedAt: 'Verified at', verify: 'Verify iMessage', requestCode: 'Send verification code', confirmCode: 'Confirm code', code: 'Code', challenge: 'Challenge',
  deliveries: 'Delivery ledger', noDeliveries: 'No deliveries yet', time: 'Time', status: 'Status', preview: 'Preview', deliveryChannel: 'Channel', error: 'Error', availability: 'Delivery available',
  source: 'Source', observed: 'Observed', yes: 'Yes', no: 'No', confirm: 'Confirm', cancel: 'Cancel', saveReady: 'Preferences saved. They will be used by the next scheduled delivery.',
} as const

const zh: Record<keyof typeof en, string> = {
  nav: '通知', title: '每日推送与通知', subtitle: '管理投递偏好、报告内容、iMessage 验证与投递记录。', loading: '正在读取通知…', unavailable: '通知暂不可用', enabled: '已启用', disabled: '已关闭', timezone: '时区', localTime: '本地时间', channel: '主渠道', channels: '通知渠道', reportTypes: '报告类型', locale: '语言',
  content: '报告内容', portfolio: '组合', market: '市场', signals: '信号', risk: '风险', sentiment: '情绪', maxLength: '报告最大长度', save: '保存偏好', saving: '保存中…', tests: '测试投递', emailTest: '测试 Email', imessageTest: '测试 iMessage', working: '处理中…', done: '操作完成。', failed: '操作不可用',
  imessage: 'iMessage', officialNumber: '官方号码', provider: '服务商', enabledPlans: '支持套餐', recipient: '接收号码', verifiedAt: '验证时间', verify: '验证 iMessage', requestCode: '发送验证码', confirmCode: '确认验证码', code: '验证码', challenge: 'Challenge', deliveries: '投递记录', noDeliveries: '暂无投递记录', time: '时间', status: '状态', preview: '预览', deliveryChannel: '渠道', error: '错误', availability: '投递可用', source: '数据源', observed: '观测时间', yes: '是', no: '否', confirm: '确认', cancel: '取消', saveReady: '偏好已保存，下一次计划投递会使用新设置。',
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface ResourceProtocolMap { 'puregamma-notifications': PureGammaNotificationsView }
  interface LocaleNamespaceMap { 'puregamma.notifications': Key }
}

interface NotificationsSectionProps { useResource: UseResource; t: (key: Key) => string; remote: NotificationsRemote }
const sectionStyle: CSSProperties = { display: 'grid', gap: 14, maxWidth: 980 }
const gridStyle: CSSProperties = { display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }
const cardStyle: CSSProperties = { border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', borderRadius: 14, background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', padding: 16, display: 'grid', gap: 12 }
const labelStyle: CSSProperties = { color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', fontSize: 12 }
const inputStyle: CSSProperties = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.28))', borderRadius: 9, padding: '8px 10px', background: 'var(--dsw-surface, transparent)', color: 'var(--dsw-text-primary, inherit)', fontSize: 13 }
const buttonStyle: CSSProperties = { border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.28))', borderRadius: 9, padding: '7px 10px', background: 'var(--dsw-surface-raised, rgba(127,127,127,.08))', color: 'var(--dsw-text-primary, inherit)', cursor: 'pointer', fontSize: 12 }

function field(label: string, control: ReactElement): ReactElement { return createElement('label', { style: { display: 'grid', gap: 6 } }, createElement('span', { style: labelStyle }, label), control) }
function checkbox(label: string, checked: boolean, onChange: (value: boolean) => void): ReactElement { return createElement('label', { style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 } }, createElement('input', { type: 'checkbox', checked, onChange: (event: { currentTarget: HTMLInputElement }) => onChange(event.currentTarget.checked) }), label) }
async function unwrap<T>(promise: Promise<RemoteResult<T>>): Promise<T> { const result = await promise; if (result.ok) return result.value; throw new Error('remote action failed') }
function splitList(value: string): string[] | undefined { const items = value.split(',').map((item) => item.trim()).filter(Boolean); return items.length ? items : undefined }
function formFromView(view: PureGammaNotificationsView): FormState { return { enabled: view.enabled === true, timezone: view.timezone ?? 'UTC', localTime: view.localTime ?? '08:00', channel: view.channel ?? 'email', channels: (view.channels ?? []).join(', '), reportTypes: (view.reportTypes ?? []).join(', '), locale: view.locale ?? 'en', includePortfolio: view.includePortfolio !== false, includeMarket: view.includeMarket !== false, includeSignals: view.includeSignals !== false, includeRisk: view.includeRisk !== false, includeSentiment: view.includeSentiment !== false, maxLength: view.maxLength === undefined ? '' : String(view.maxLength) } }
function toUpdate(form: FormState, current: PureGammaNotificationsView): PureGammaDailyBriefUpdate { const maxLength = form.maxLength.trim() ? Number(form.maxLength) : undefined; return { enabled: form.enabled, timezone: form.timezone.trim(), localTime: form.localTime.trim(), channel: form.channel.trim(), channels: splitList(form.channels), reportTypes: splitList(form.reportTypes), locale: form.locale.trim(), includePortfolio: form.includePortfolio, includeMarket: form.includeMarket, includeSignals: form.includeSignals, includeRisk: form.includeRisk, includeSentiment: form.includeSentiment, quietHours: current.quietHours, maxLength: maxLength !== undefined && Number.isFinite(maxLength) ? maxLength : undefined } }

function NotificationsSection({ useResource, t, remote }: NotificationsSectionProps): ReactElement {
  const snapshot = useResource<'puregamma-notifications'>(ADDRESS)
  const [form, setForm] = useState<FormState>({ enabled: false, timezone: 'UTC', localTime: '08:00', channel: 'email', channels: 'email', reportTypes: '', locale: 'en', includePortfolio: true, includeMarket: true, includeSignals: true, includeRisk: true, includeSentiment: true, maxLength: '' })
  const [recipient, setRecipient] = useState('')
  const [code, setCode] = useState('')
  const [challengeId, setChallengeId] = useState('')
  const [busy, setBusy] = useState<string | undefined>()
  const [message, setMessage] = useState<string | undefined>()

  useEffect(() => {
    if (snapshot.value?.available) {
      setForm(formFromView(snapshot.value))
      setRecipient(snapshot.value.imessage?.recipient ?? '')
    }
  }, [snapshot.value?.observedAt])

  if (snapshot.status === 'loading' || snapshot.status === 'none') return createElement('section', { style: sectionStyle }, createElement('p', { style: labelStyle }, t('loading')))
  if (snapshot.status === 'failed' || snapshot.value === undefined || !snapshot.value.available) return createElement('section', { style: sectionStyle }, createElement('div', { style: cardStyle }, createElement('strong', null, t('unavailable')), snapshot.value?.reason ? createElement('span', { style: labelStyle }, snapshot.value.reason) : null))

  const view = snapshot.value
  const run = async (key: string, operation: () => Promise<PureGammaNotificationActionResult>): Promise<PureGammaNotificationActionResult | undefined> => {
    setBusy(key); setMessage(undefined)
    try { const result = await operation(); if (!result.available) { setMessage(result.reason ?? t('failed')); return result }; setMessage(t('done')); return result } catch { setMessage(t('failed')); return undefined } finally { setBusy(undefined) }
  }

  const save = async (): Promise<void> => { await run('save', () => unwrap(remote.notificationsUpdateDailyBrief(toUpdate(form, view)))) }
  const testEmail = async (): Promise<void> => { await run('email-test', () => unwrap(remote.notificationsTestEmail())) }
  const testImessage = async (): Promise<void> => { await run('imessage-test', () => unwrap(remote.notificationsTestImessage())) }
  const requestVerification = async (): Promise<void> => { const result = await run('verify-request', () => unwrap(remote.notificationsRequestImessageVerification(recipient))); if (result?.challengeId) setChallengeId(result.challengeId) }
  const confirmVerification = async (): Promise<void> => { await run('verify-confirm', () => unwrap(remote.notificationsConfirmImessageVerification(challengeId, code))) }

  const deliveries = view.deliveries.slice(0, 30)
  return createElement('section', { style: sectionStyle },
    createElement('header', null, createElement('h2', { style: { margin: 0, fontSize: 18, fontWeight: 620 } }, t('title')), createElement('p', { style: { ...labelStyle, margin: '6px 0 0' } }, t('subtitle'))),
    message ? createElement('div', { style: cardStyle }, createElement('span', { style: labelStyle }, message)) : null,
    createElement('div', { style: cardStyle },
      createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' } }, createElement('strong', null, t('nav')), createElement('span', { style: { ...labelStyle, fontSize: 11 } }, view.enabled === true ? t('enabled') : t('disabled'))),
      createElement('div', { style: gridStyle },
        field(t('timezone'), createElement('input', { style: inputStyle, value: form.timezone, onChange: (e: { currentTarget: HTMLInputElement }) => setForm({ ...form, timezone: e.currentTarget.value }) })),
        field(t('localTime'), createElement('input', { type: 'time', style: inputStyle, value: form.localTime, onChange: (e: { currentTarget: HTMLInputElement }) => setForm({ ...form, localTime: e.currentTarget.value }) })),
        field(t('channel'), createElement('select', { style: inputStyle, value: form.channel, onChange: (e: { currentTarget: HTMLSelectElement }) => setForm({ ...form, channel: e.currentTarget.value }) }, ...['email', 'telegram', 'slack', 'imessage', 'push'].map((value) => createElement('option', { key: value, value }, value)))),
        field(t('locale'), createElement('select', { style: inputStyle, value: form.locale, onChange: (e: { currentTarget: HTMLSelectElement }) => setForm({ ...form, locale: e.currentTarget.value }) }, createElement('option', { value: 'en' }, 'English'), createElement('option', { value: 'zh' }, '中文'))),
        field(t('channels'), createElement('input', { style: inputStyle, value: form.channels, placeholder: 'email, telegram', onChange: (e: { currentTarget: HTMLInputElement }) => setForm({ ...form, channels: e.currentTarget.value }) })),
        field(t('reportTypes'), createElement('input', { style: inputStyle, value: form.reportTypes, placeholder: 'daily, risk, signals', onChange: (e: { currentTarget: HTMLInputElement }) => setForm({ ...form, reportTypes: e.currentTarget.value }) })),
        field(t('maxLength'), createElement('input', { type: 'number', min: 256, max: 50000, style: inputStyle, value: form.maxLength, onChange: (e: { currentTarget: HTMLInputElement }) => setForm({ ...form, maxLength: e.currentTarget.value }) })),
      ),
      checkbox(t('enabled'), form.enabled, (enabled) => setForm({ ...form, enabled })),
      createElement('div', { style: { display: 'grid', gap: 8 } }, createElement('strong', null, t('content')), checkbox(t('portfolio'), form.includePortfolio, (value) => setForm({ ...form, includePortfolio: value })), checkbox(t('market'), form.includeMarket, (value) => setForm({ ...form, includeMarket: value })), checkbox(t('signals'), form.includeSignals, (value) => setForm({ ...form, includeSignals: value })), checkbox(t('risk'), form.includeRisk, (value) => setForm({ ...form, includeRisk: value })), checkbox(t('sentiment'), form.includeSentiment, (value) => setForm({ ...form, includeSentiment: value }))),
      createElement('button', { type: 'button', disabled: busy !== undefined, style: buttonStyle, onClick: () => { void save() } }, busy === 'save' ? t('saving') : t('save')),
    ),
    createElement('div', { style: gridStyle },
      createElement('div', { style: cardStyle }, createElement('strong', null, t('tests')), createElement('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 8 } }, createElement('button', { type: 'button', disabled: busy !== undefined, style: buttonStyle, onClick: () => { void testEmail() } }, busy === 'email-test' ? t('working') : t('emailTest')), createElement('button', { type: 'button', disabled: busy !== undefined, style: buttonStyle, onClick: () => { void testImessage() } }, busy === 'imessage-test' ? t('working') : t('imessageTest')))),
      createElement('div', { style: cardStyle }, createElement('strong', null, t('imessage')), createElement('div', { style: gridStyle }, field(t('officialNumber'), createElement('span', { style: labelStyle }, view.imessage?.officialNumber ?? '—')), field(t('provider'), createElement('span', { style: labelStyle }, view.imessage?.provider ?? '—')), field(t('enabledPlans'), createElement('span', { style: labelStyle }, (view.imessage?.enabledPlans ?? []).join(', ') || '—')), field(t('recipient'), createElement('input', { style: inputStyle, value: recipient, onChange: (e: { currentTarget: HTMLInputElement }) => setRecipient(e.currentTarget.value) }))),
        view.imessage?.recipientVerifiedAt ? createElement('span', { style: labelStyle }, `${t('verifiedAt')}: ${view.imessage.recipientVerifiedAt}`) : createElement('div', { style: { display: 'grid', gap: 8 } }, createElement('button', { type: 'button', disabled: busy !== undefined || !recipient.trim(), style: buttonStyle, onClick: () => { void requestVerification() } }, busy === 'verify-request' ? t('working') : t('requestCode')), challengeId ? createElement('div', { style: { display: 'grid', gap: 8 } }, field(t('challenge'), createElement('input', { style: inputStyle, value: challengeId, onChange: (e: { currentTarget: HTMLInputElement }) => setChallengeId(e.currentTarget.value) })), field(t('code'), createElement('input', { style: inputStyle, value: code, onChange: (e: { currentTarget: HTMLInputElement }) => setCode(e.currentTarget.value) })), createElement('button', { type: 'button', disabled: busy !== undefined || !code.trim(), style: buttonStyle, onClick: () => { void confirmVerification() } }, busy === 'verify-confirm' ? t('working') : t('confirmCode'))) : null),
      ),
    ),
    createElement('div', { style: cardStyle }, createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12 } }, createElement('strong', null, t('deliveries')), createElement('span', { style: labelStyle }, `${t('availability')}: ${view.deliveryAvailable === true ? t('yes') : t('no')}`)), deliveries.length ? createElement('div', { style: { overflowX: 'auto' } }, createElement('table', { style: { width: '100%', minWidth: 650, borderCollapse: 'collapse', fontSize: 12 } }, createElement('thead', null, createElement('tr', null, ...[t('time'), t('deliveryChannel'), t('status'), t('preview'), t('error')].map((head) => createElement('th', { key: head, style: { textAlign: 'left', padding: '7px 8px', borderBottom: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.18))' } }, head)))), createElement('tbody', null, ...deliveries.map((item, index) => createElement('tr', { key: item.id ?? `${item.createdAt ?? 'delivery'}-${index}` }, createElement('td', { style: { padding: 8 } }, item.sentAt ?? item.createdAt ?? '—'), createElement('td', { style: { padding: 8 } }, item.channel ?? '—'), createElement('td', { style: { padding: 8 } }, item.status ?? '—'), createElement('td', { style: { padding: 8, maxWidth: 300 } }, item.messagePreview ?? '—'), createElement('td', { style: { padding: 8 } }, item.error ?? '—')))))) : createElement('p', { style: labelStyle }, t('noDeliveries'))),
    createElement('div', { style: { ...labelStyle, display: 'flex', gap: 12, flexWrap: 'wrap' } }, createElement('span', null, `${t('source')}: ${view.source}`), createElement('span', null, `${t('observed')}: ${view.observedAt}`)),
  )
}

function wait(ms: number, signal: AbortSignal): Promise<void> { if (signal.aborted) return Promise.resolve(); return new Promise((resolve) => { const done = (): void => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }; const timer = setTimeout(done, ms); signal.addEventListener('abort', done, { once: true }) }) }

export const inject = ['slots', 'locale', 'resources', 'remote', 'remote.puregammaClient']
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-notifications: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  ctx.effect(() => ctx.resources.register<'puregamma-notifications'>({ protocol: 'puregamma-notifications', async *open(_address, { signal }) { while (!signal.aborted) { yield await ctx.remote.puregammaClient.notifications(); await wait(POLL_MS, signal) } } }), 'puregamma-notifications: resource provider')
  ctx.slots.inject('settings.section', () => ctx.slots.register({ name: 'settings.section', id: 'puregamma-notifications', order: 40, label: () => t('nav'), inject: () => ({ t, remote: ctx.remote.puregammaClient }) }, NotificationsSection))
}
