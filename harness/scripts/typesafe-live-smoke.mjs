#!/usr/bin/env node
/**
 * Explicit opt-in, ONE paid request using synthetic text only. Not part of CI.
 * Never log or store the API key, Authorization header, raw user memory or
 * response body. This script does not execute any PureGamma plugin action.
 * Rotate any API key that was previously pasted into a chat before using it.
 */
const enabled = process.argv.length === 3 && process.argv[2] === '--live' && process.env.TYPESAFE_LIVE_SMOKE === 'YES_ONE_PAID_CALL'
if (!enabled) {
  console.error('BLOCKED: use --live with TYPESAFE_LIVE_SMOKE=YES_ONE_PAID_CALL for one explicit paid test.')
  process.exit(2)
}
const key = process.env.TYPESAFE_API_KEY
if (typeof key !== 'string' || key.trim().length < 16) {
  console.error('BLOCKED: server-side TYPESAFE_API_KEY is missing or invalid; no request sent.')
  process.exit(2)
}
const question = {
  state: {
    request: 'Show a summary of the latest cryptocurrency market headlines for research; do not trade or send messages.',
    eligibleCapabilities: ['market-data', 'research', 'none'],
    mode: 'dry-decision-no-action',
  },
  model: 'jev-latest',
  questions: {
    route: {
      type: 'choice',
      instructions: 'Select exactly one listed capability for reading cryptocurrency market headlines; select none if none fits. This is classification only, not permission to run a tool.',
      criteria: {
        'market-data': 'Read provider-fresh market news and market state',
        research: 'Read curated research reports and existing briefs',
        none: 'No listed capability can fulfill this request',
      },
    },
  },
}

const controller = new AbortController()
const timeout = setTimeout(() => controller.abort(), 12_000)
try {
  // No retries, no redirects, and no raw response printing: only one billable POST.
  const response = await fetch('https://api.typesafe.ai/v1/systemone', {
    method: 'POST',
    redirect: 'error',
    signal: controller.signal,
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(question),
  })
  if (!response.ok) throw new Error(`TypeSafe returned HTTP ${response.status}`)
  const result = await response.json()
  const route = result?.answers?.route
  const usage = result?.usage
  const allowed = new Set(['market-data', 'research', 'none'])
  if (result?.model === undefined || route?.type !== 'choice' || !allowed.has(route.choice) ||
      !Number.isFinite(route.confidence) || route.confidence < 0 || route.confidence > 1 ||
      !Number.isSafeInteger(usage?.input_tokens) || usage.input_tokens < 0 ||
      !Number.isSafeInteger(usage?.output_tokens) || usage.output_tokens < 0) {
    throw new Error('TypeSafe returned an invalid typed response')
  }
  console.log(JSON.stringify({ status: 'real-paid-response-validated', model: result.model, selected: route.choice,
    confidence: route.confidence, inputTokens: usage.input_tokens, outputTokens: usage.output_tokens,
    pluginsExecuted: 0, userMemorySent: false }))
} catch (error) {
  // Suppress exception messages from providers that could echo request details.
  console.error(`BLOCKED: paid smoke did not validate (${error instanceof Error && error.name === 'AbortError' ? 'timeout' : 'request-or-schema-error'}). No plugin action executed.`)
  process.exitCode = 1
} finally {
  clearTimeout(timeout)
}
