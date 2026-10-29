import assert from 'node:assert/strict'
import test from 'node:test'
import { decide, startMockLlm } from './fixtures/mock-llm.mjs'

// The end-to-end mock model must be deterministic and local-only, and both
// wire formats (OpenAI chat completions for the legacy API, Anthropic
// messages for DSH) must yield the same decisions.

test('decisions are a pure function of the request', () => {
  const turn = text => ({ role: 'user', text, lead: text })
  assert.deepEqual(decide({ system: '', turns: [turn('hello there')], tools: [] }), { text: 'Echo: hello there', slow: false })
  assert.deepEqual(decide({ system: '', turns: [turn('q [[tool:market_snapshot {"instruments":[]}]]')], tools: ['market_snapshot'] }), { tool: { name: 'market_snapshot', args: { instruments: [] } } })
  assert.equal(decide({ system: '', turns: [turn('q [[tool:market_snapshot]]')], tools: [] }).text, 'Echo: q', 'an unoffered tool is never called')
  assert.match(decide({ system: '', turns: [turn('q [[tool:x]]'), { role: 'assistant', text: '' }, { role: 'tool', text: '{"a":1}' }], tools: ['x'] }).text, /^Tool x returned: \{"a":1\}/)
  assert.equal(decide({ system: '', turns: [{ ...turn('look'), images: 2 }], tools: [] }).text, 'I see 2 image(s).')
  assert.equal(decide({ system: '', turns: [turn('Classify the user message into exactly one of these labels: a, b')], tools: [] }).text, 'other')
  assert.equal(decide({ system: '', turns: [{ role: 'user', text: 'hi\nCurrent runtime context …', lead: 'hi' }], tools: [] }).text, 'Echo: hi')
})

test('both wire formats, streaming and not, on 127.0.0.1 only', async () => {
  const mock = await startMockLlm(0)
  try {
    assert.match(mock.url, /^http:\/\/127\.0\.0\.1:\d+$/)
    assert.equal(mock.server.address().address, '127.0.0.1')
    const post = async (path, body) => (await fetch(`${mock.url}${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).text()
    const openai = JSON.parse(await post('/v1/chat/completions', { model: 'm', messages: [{ role: 'user', content: 'hi' }] }))
    assert.equal(openai.choices[0].message.content, 'Echo: hi')
    const stream = await post('/v1/chat/completions', { model: 'm', stream: true, messages: [{ role: 'user', content: 'hi' }] })
    assert.ok(stream.trim().endsWith('data: [DONE]'))
    const anthropic = await post('/v1/messages', { model: 'm', stream: true, messages: [{ role: 'user', content: [{ type: 'text', text: 'hi' }, { type: 'text', text: 'runtime context' }] }] })
    assert.match(anthropic, /"text_delta","text":"Echo: hi"/)
    assert.match(anthropic, /event: message_stop/)
    assert.equal((await fetch(`${mock.url}/v1/files`, { method: 'POST' })).status, 404, 'DSH falls back to inline images')
    assert.equal(mock.requests.length, 3)
  } finally {
    await mock.close()
  }
})
