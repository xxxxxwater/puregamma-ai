import { createElement } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { UseResource } from '@deepseek-ai/dsh-client-resources/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-api-gateway/client'
import type {} from '@puregamma/dsh-client-gateway/remote'
import type { PureGammaAccountView } from '@puregamma/dsh-client-gateway'

const ADDRESS = 'dsh-resource://puregamma-account/current'
const NS = 'puregamma.account'
const POLL_MS = 30_000

const en = {
  nav: 'Account', title: 'PureGamma account', subtitle: 'Identity and plan state from the currently installed account provider.',
  loading: 'Loading account…', unavailable: 'Account unavailable', identity: 'Identity', plan: 'Plan', credits: 'Credits',
  provider: 'Sign-in provider', verification: 'Email verification', verified: 'Verified', unverified: 'Not verified',
  methods: 'Login methods', locale: 'Locale', lastLogin: 'Last login', source: 'Source', observed: 'Observed', missing: '—',
} as const
const zh: Record<keyof typeof en, string> = {
  nav: '账户', title: 'PureGamma 账户', subtitle: '来自当前已安装账户 Provider 的身份与套餐状态。',
  loading: '正在读取账户…', unavailable: '账户不可用', identity: '身份', plan: '套餐', credits: 'Credits',
  provider: '登录 Provider', verification: '邮箱验证', verified: '已验证', unverified: '未验证', methods: '登录方式',
  locale: '语言', lastLogin: '最近登录', source: '数据源', observed: '观测时间', missing: '—',
}
type Key = keyof typeof en

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface ResourceProtocolMap { 'puregamma-account': PureGammaAccountView }
  interface LocaleNamespaceMap { 'puregamma.account': Key }
}

interface AccountSectionProps {
  useResource: UseResource
  t: (key: Key) => string
}

const sectionStyle: CSSProperties = { display: 'grid', gap: 14, maxWidth: 760 }
const cardStyle: CSSProperties = {
  border: '1px solid var(--dsw-border-subtle, rgba(127,127,127,.22))', borderRadius: 14,
  background: 'var(--dsw-surface-raised, rgba(127,127,127,.035))', padding: 16, display: 'grid', gap: 12,
}
const gridStyle: CSSProperties = { display: 'grid', gridTemplateColumns: 'minmax(120px, 0.8fr) minmax(160px, 1.6fr)', gap: '10px 18px' }
const labelStyle: CSSProperties = { color: 'var(--dsw-text-secondary, rgba(127,127,127,.9))', fontSize: 13 }
const valueStyle: CSSProperties = { color: 'var(--dsw-text-primary, inherit)', fontSize: 13, overflowWrap: 'anywhere' }

function row(label: string, value: string | number | undefined, missing: string): ReactElement[] {
  return [
    createElement('div', { key: `${label}-label`, style: labelStyle }, label),
    createElement('div', { key: `${label}-value`, style: valueStyle }, value === undefined || value === '' ? missing : String(value)),
  ]
}

function AccountSection({ useResource, t }: AccountSectionProps): ReactElement {
  const snapshot = useResource<'puregamma-account'>(ADDRESS)
  if (snapshot.status === 'loading' || snapshot.status === 'none') {
    return createElement('section', { style: sectionStyle }, createElement('p', { style: labelStyle }, t('loading')))
  }
  if (snapshot.status === 'failed' || snapshot.value === undefined || !snapshot.value.available) {
    const reason = snapshot.value?.reason
    return createElement('section', { style: sectionStyle },
      createElement('div', { style: cardStyle },
        createElement('strong', null, t('unavailable')),
        reason ? createElement('span', { style: labelStyle }, reason) : null,
      ),
    )
  }
  const account = snapshot.value
  return createElement('section', { style: sectionStyle },
    createElement('header', null,
      createElement('h2', { style: { margin: 0, fontSize: 18, fontWeight: 620 } }, t('title')),
      createElement('p', { style: { ...labelStyle, margin: '6px 0 0' } }, t('subtitle')),
    ),
    createElement('div', { style: cardStyle },
      createElement('div', { style: gridStyle },
        ...row(t('identity'), account.name ?? account.email, t('missing')),
        ...row('Email', account.email, t('missing')),
        ...row(t('plan'), account.plan ?? account.membershipTier, t('missing')),
        ...row(t('credits'), account.creditBalance, t('missing')),
        ...row(t('provider'), account.authProvider, t('missing')),
        ...row(t('verification'), account.emailVerified === true ? t('verified') : t('unverified'), t('missing')),
        ...row(t('methods'), account.loginMethods?.join(', '), t('missing')),
        ...row(t('locale'), account.locale, t('missing')),
        ...row(t('lastLogin'), account.lastLoginAt, t('missing')),
      ),
    ),
    createElement('div', { style: { ...labelStyle, display: 'flex', gap: 12, flexWrap: 'wrap' } },
      createElement('span', null, `${t('source')}: ${account.source}`),
      createElement('span', null, `${t('observed')}: ${account.observedAt}`),
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
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'puregamma-account: dictionaries')
  const t = ctx.locale.bind(NS) as (key: Key) => string
  ctx.effect(() => ctx.resources.register<'puregamma-account'>({
    protocol: 'puregamma-account',
    async *open(_address, { signal }) {
      while (!signal.aborted) {
        yield await ctx.remote.puregammaClient.account()
        await wait(POLL_MS, signal)
      }
    },
  }), 'puregamma-account: resource provider')
  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section', id: 'puregamma-account', order: 20, label: () => t('nav'), inject: () => ({ t }),
  }, AccountSection))
}
