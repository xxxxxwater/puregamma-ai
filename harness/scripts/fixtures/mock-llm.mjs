// Deterministic local LLM for end-to-end runs. Listens on 127.0.0.1 only and
// never calls out. Speaks the OpenAI chat-completions API and the
// Anthropic-style messages API, streaming and not.
//
//   node mock-llm.mjs [port]            (prints `mock-llm: http://127.0.0.1:<port>`)
//   import { startMockLlm } from './mock-llm.mjs'
//
// The answer depends only on the request, so both paths (DSH and the legacy
// FastAPI agent) get identical behaviour:
// - last user turn contains `[[tool:<name> <json args>]]` and the request
//   offers that tool → one tool call; after the tool result → "Tool <name>
//   returned: <first 80 chars of the result>";
// - `[[slow]]` → 40 streamed chunks, 150 ms apart (for cancel/reconnect);
// - images in the last user turn → "I see N image(s)";
// - the legacy API's intent-classification call → "other";
// - a system/developer prompt containing `SKILL:<name>` → reply mentions it;
// - otherwise → "Echo: <first 60 chars of the last user text>".
// GET /__mock/requests returns the recorded requests (newest last).
import http from 'node:http'
import process from 'node:process'
import { pathToFileURL } from 'node:url'

const TOOL = /\[\[tool:([A-Za-z0-9_.-]+)(?:\s+(\{.*?\}))?\]\]/s

function textOf(content) {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  return content.map(part => (typeof part === 'string' ? part : part?.text ?? (typeof part?.content === 'string' ? part.content : ''))).join('\n')
}
const imagesIn = content => Array.isArray(content) ? content.filter(part => part?.type === 'image_url' || part?.type === 'image' || part?.type === 'input_image').length : 0

/** Normalise both wire formats into { system, turns: [{role, text, images, toolResult}], tools: [names] }. */
function normalise(body, anthropic) {
  const turns = []
  let system = anthropic ? textOf(body.system) : ''
  for (const message of body.messages ?? []) {
    if (!anthropic && (message.role === 'system' || message.role === 'developer')) { system += `\n${textOf(message.content)}`; continue }
    if (!anthropic && message.role === 'tool') { turns.push({ role: 'tool', text: textOf(message.content) }); continue }
    if (anthropic && Array.isArray(message.content) && message.content.some(part => part?.type === 'tool_result')) {
      const result = message.content.find(part => part?.type === 'tool_result')
      turns.push({ role: 'tool', text: textOf(result.content) })
      continue
    }
    // `lead` is the first text block: DSH appends runtime-context blocks to the user turn.
    const lead = Array.isArray(message.content) ? (message.content.find(part => part?.type === 'text')?.text ?? '') : textOf(message.content)
    turns.push({ role: message.role, text: textOf(message.content), lead, images: imagesIn(message.content) })
  }
  const tools = (body.tools ?? []).map(tool => tool.function?.name ?? tool.name).filter(Boolean)
  return { system, turns, tools }
}

/** The deterministic decision: either text or one tool call. */
export function decide({ system, turns, tools }) {
  const last = turns.at(-1)
  const lastUser = [...turns].reverse().find(turn => turn.role === 'user')
  const skill = /SKILL:([A-Za-z0-9_.-]+)/.exec(system ?? '')?.[1]
  if (last?.role === 'tool') {
    const call = [...turns].reverse().find(turn => turn.role === 'user' && TOOL.test(turn.text))
    const name = call ? TOOL.exec(call.text)[1] : 'tool'
    return { text: `Tool ${name} returned: ${last.text.replace(/\s+/g, ' ').slice(0, 80)}` }
  }
  const text = lastUser?.text ?? ''
  // The legacy API's intent classifier: "other" keeps its normal tool chain.
  if (/^Classify the user message into exactly one of these labels/.test(text)) return { text: 'other' }
  const tool = TOOL.exec(text)
  if (tool && tools.includes(tool[1])) {
    let args = {}
    try { args = tool[2] ? JSON.parse(tool[2]) : {} } catch {}
    return { tool: { name: tool[1], args } }
  }
  if (lastUser?.images) return { text: `I see ${lastUser.images} image(s).` }
  const echo = `Echo: ${(lastUser?.lead ?? text).replace(/\[\[[^\]]*\]\]/g, '').replace(/\s+/g, ' ').trim().slice(0, 60)}`
  return { text: skill ? `${echo} (skill ${skill})` : echo, slow: text.includes('[[slow]]') }
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const chunksOf = (text, slow) => slow ? Array.from({ length: 40 }, (_, i) => `${i === 0 ? text : ''} part${i + 1}`) : text.match(/.{1,12}/gs) ?? ['']

async function openai(res, body, answer, model) {
  const id = `chatcmpl-mock-${Date.now()}`
  const created = Math.floor(Date.now() / 1000)
  const usage = { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 }
  const toolCall = answer.tool && { index: 0, id: `call_${answer.tool.name}_1`, type: 'function', function: { name: answer.tool.name, arguments: JSON.stringify(answer.tool.args) } }
  if (!body.stream) {
    res.writeHead(200, { 'content-type': 'application/json' })
    return res.end(JSON.stringify({
      id, object: 'chat.completion', created, model,
      choices: [{ index: 0, finish_reason: answer.tool ? 'tool_calls' : 'stop', message: { role: 'assistant', content: answer.tool ? null : answer.text, ...(toolCall ? { tool_calls: [{ ...toolCall, index: undefined }] } : {}) } }],
      usage,
    }))
  }
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
  const send = payload => res.write(`data: ${JSON.stringify({ id, object: 'chat.completion.chunk', created, model, ...payload })}\n\n`)
  send({ choices: [{ index: 0, delta: { role: 'assistant', content: '' }, finish_reason: null }] })
  if (answer.tool) {
    send({ choices: [{ index: 0, delta: { tool_calls: [toolCall] }, finish_reason: null }] })
  } else {
    for (const piece of chunksOf(answer.text, answer.slow)) {
      if (res.destroyed) return
      send({ choices: [{ index: 0, delta: { content: piece }, finish_reason: null }] })
      if (answer.slow) await sleep(150)
    }
  }
  send({ choices: [{ index: 0, delta: {}, finish_reason: answer.tool ? 'tool_calls' : 'stop' }], usage })
  res.end('data: [DONE]\n\n')
}

async function anthropic(res, body, answer, model) {
  const id = `msg_mock_${Date.now()}`
  const usage = { input_tokens: 10, output_tokens: 5 }
  const block = answer.tool ? { type: 'tool_use', id: `toolu_${answer.tool.name}_1`, name: answer.tool.name, input: answer.tool.args } : { type: 'text', text: answer.text }
  const stop = answer.tool ? 'tool_use' : 'end_turn'
  if (!body.stream) {
    res.writeHead(200, { 'content-type': 'application/json' })
    return res.end(JSON.stringify({ id, type: 'message', role: 'assistant', model, content: [block], stop_reason: stop, stop_sequence: null, usage }))
  }
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
  const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`)
  send('message_start', { message: { id, type: 'message', role: 'assistant', model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 0 } } })
  if (answer.tool) {
    send('content_block_start', { index: 0, content_block: { type: 'tool_use', id: block.id, name: block.name, input: {} } })
    send('content_block_delta', { index: 0, delta: { type: 'input_json_delta', partial_json: JSON.stringify(block.input) } })
  } else {
    send('content_block_start', { index: 0, content_block: { type: 'text', text: '' } })
    for (const piece of chunksOf(answer.text, answer.slow)) {
      if (res.destroyed) return
      send('content_block_delta', { index: 0, delta: { type: 'text_delta', text: piece } })
      if (answer.slow) await sleep(150)
    }
  }
  send('content_block_stop', { index: 0 })
  send('message_delta', { delta: { stop_reason: stop, stop_sequence: null }, usage: { output_tokens: 5 } })
  send('message_stop', {})
  res.end()
}

export async function startMockLlm(port = 0) {
  const requests = []
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://mock')
    if (req.method === 'GET' && url.pathname === '/__mock/requests') {
      res.writeHead(200, { 'content-type': 'application/json' })
      return res.end(JSON.stringify(requests))
    }
    if (req.method === 'GET' && /\/models$/.test(url.pathname)) {
      res.writeHead(200, { 'content-type': 'application/json' })
      return res.end(JSON.stringify({ object: 'list', data: [{ id: 'mock-model', object: 'model', owned_by: 'mock' }] }))
    }
    let raw = ''
    req.setEncoding('utf8')
    req.on('data', chunk => { raw += chunk })
    req.on('end', () => {
      let body = {}
      try { body = JSON.parse(raw || '{}') } catch {}
      const isAnthropic = /\/messages$/.test(url.pathname)
      const isOpenAI = /\/chat\/completions$/.test(url.pathname)
      if (!isAnthropic && !isOpenAI) {
        res.writeHead(404, { 'content-type': 'application/json' })
        return res.end(JSON.stringify({ error: { message: `mock-llm has no ${url.pathname}` } }))
      }
      const normalised = normalise(body, isAnthropic)
      const answer = decide(normalised)
      requests.push({ at: Date.now(), path: url.pathname, model: body.model, stream: Boolean(body.stream), tools: normalised.tools, turns: normalised.turns.length, lastUser: normalised.turns.filter(turn => turn.role === 'user').at(-1)?.text?.slice(0, 200) ?? '', images: normalised.turns.at(-1)?.images ?? 0, corpus: [normalised.system, ...normalised.turns.map(turn => turn.text)].join('\n').slice(0, 20_000), answer: answer.tool ? { tool: answer.tool.name } : { text: answer.text.slice(0, 120) } })
      if (requests.length > 500) requests.shift()
      const model = body.model ?? 'mock-model'
      void (isAnthropic ? anthropic(res, body, answer, model) : openai(res, body, answer, model))
    })
  })
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve))
  const url = `http://127.0.0.1:${server.address().port}`
  return { server, url, requests, close: () => new Promise(resolve => { server.closeAllConnections?.(); server.close(resolve) }) }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const mock = await startMockLlm(Number(process.argv[2] ?? 0))
  console.log(`mock-llm: ${mock.url}`)
}
