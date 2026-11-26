import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement } from 'react'
import renderer from 'react-test-renderer'
import { apply } from '../plugins/ui-notifications/src/client/index.ts'

test('notification edits survive polling and are isolated by account', async () => {
  let Section
  apply({
    effect: callback => callback(),
    locale: { register() {}, bind: () => key => key },
    resources: { register() {} },
    slots: { inject: (_, callback) => callback(), register: (_, component) => { Section = component } },
  })
  const time = seconds => new Date(Date.UTC(2026, 0, 1) + seconds * 1000).toISOString()
  let snapshot = { status: 'ready', value: { accountId: 'first', available: true, observedAt: time(0),
    timezone: 'UTC', maxLength: 1000, imessage: { recipient: 'first@example.invalid' }, deliveries: [] } }
  let submitted
  const remote = {
    notificationsUpdateDailyBrief: async request => {
      submitted = request
      return { ok: true, value: { available: true, observedAt: time(70), preferences: { ...request, maxLength: 3000 } } }
    },
    notificationsRequestImessageVerification: async () => ({ ok: true, value: { available: true, challengeId: 'challenge-1' } }),
    notificationsConfirmImessageVerification: async () => ({ ok: true, value: { available: true, observedAt: time(68), recipient: 'new@example.invalid' } }),
  }
  const element = () => createElement(Section, { useResource: () => snapshot, t: key => key, remote })
  let mounted
  renderer.act(() => { mounted = renderer.create(element()) })
  const input = key => mounted.root.findAllByType('label').find(label =>
    label.findAllByType('span')[0]?.children[0] === key)?.findByType('input')
  const change = (key, value) => renderer.act(() => input(key).props.onChange({ currentTarget: { value } }))
  const click = async key => {
    const button = mounted.root.findAllByType('button').find(button => button.children[0] === key)
    assert.ok(button, key)
    await renderer.act(async () => button.props.onClick())
  }
  const refresh = (at, patch = {}) => renderer.act(() => {
    snapshot = { status: 'ready', value: { ...snapshot.value, observedAt: time(at), ...patch } }
    mounted.update(element())
  })
  change('maxLength', '4000')
  change('recipient', 'new@example.invalid')
  await click('requestCode')
  change('code', '123456')
  refresh(30, { timezone: 'Asia/Shanghai' })
  refresh(60)
  assert.equal(input('maxLength').props.value, '4000')
  assert.equal(input('recipient').props.value, 'new@example.invalid')
  assert.equal(input('code').props.value, '123456')
  assert.equal(mounted.root.findByProps({ role: 'status' }).children[0], 'remoteChanged')

  renderer.act(() => { snapshot.status = 'failed'; mounted.update(element()) })
  assert.equal(input('recipient'), undefined)
  refresh(65)
  assert.equal(input('code').props.value, '123456')
  await click('confirmCode')
  assert.equal(input('code'), undefined)
  await click('save')
  assert.equal(submitted.maxLength, 4000)
  assert.equal('quietHours' in submitted, false)
  assert.equal(input('maxLength').props.value, '3000')
  refresh(69) // Late result from a read that started before the save.
  assert.equal(input('maxLength').props.value, '3000')
  refresh(75, { maxLength: 2900 })
  assert.equal(input('maxLength').props.value, '2900')

  change('timezone', 'Europe/Berlin')
  await click('discard')
  assert.equal(input('timezone').props.value, 'Asia/Shanghai')
  change('timezone', 'Europe/Berlin')
  change('recipient', 'unsaved@example.invalid')
  await click('requestCode')
  change('code', '543210')
  refresh(90, { accountId: 'second', timezone: 'UTC', imessage: {} })
  assert.equal(input('timezone').props.value, 'UTC')
  assert.equal(input('recipient').props.value, '')
  assert.equal(input('code'), undefined)
  // An older backend may omit account identity. Never reuse private edits
  // across two snapshots whose owners cannot be compared.
  refresh(100, { accountId: undefined })
  change('recipient', 'unsaved@example.invalid')
  refresh(130)
  assert.equal(input('recipient').props.value, '')
  renderer.act(() => mounted.unmount())
})

test('a poll started before a successful write keeps its earlier timestamp', async t => {
  const { PureGammaClientGateway } = await import('../packages/client-gateway/src/index.ts')
  const start = Date.UTC(2026, 0, 1)
  t.mock.timers.enable({ apis: ['Date'], now: start })
  const devices = Promise.withResolvers()
  const document = payload => ({ observedAt: new Date().toISOString(), source: 'test', payload })
  const service = {
    dailyBrief: async () => document({ account_id: 'first', preference: { max_length: 1000 } }),
    deliveries: async () => document({ deliveries: [] }),
    imessageConfig: async () => document({}),
    devices: () => devices.promise,
    updateDailyBrief: async () => document({ preference: { max_length: 3000 } }),
  }
  const context = { ctx: { get: () => service } }
  const poll = PureGammaClientGateway.prototype.notifications.call(context)
  t.mock.timers.tick(1000)
  const receipt = await PureGammaClientGateway.prototype.notificationsUpdateDailyBrief.call(context, { maxLength: 4000 })
  devices.resolve(document({}))
  const snapshot = await poll
  assert.equal(snapshot.accountId, 'first')
  assert.equal(snapshot.maxLength, 1000)
  assert.equal(receipt.preferences.maxLength, 3000)
  assert.ok(snapshot.observedAt < receipt.observedAt)
})
