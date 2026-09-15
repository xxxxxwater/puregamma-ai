import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { OptionsDocument, OptionsSurfaceType } from '@puregamma/dsh-options'
import type {} from '@puregamma/dsh-options'

export const name = 'puregamma-tool-options'
export const inject = ['tools', 'pgOptions']

const OPTION_KINDS = ['chain', 'long-gamma', 'surface', 'surface-tickers', 'earnings-gamma'] as const
const PROVIDER_STATES = ['healthy', 'degraded', 'unavailable'] as const
const SURFACE_TYPES = ['mark_iv', 'mark_price', 'gamma', 'theta', 'vega', 'spread_pct'] as const

function documentSchema() {
  return {
    type: 'object' as const,
    additionalProperties: false,
    properties: {
      kind: { type: 'string' as const, required: true as const, enum: [...OPTION_KINDS] },
      underlying: { type: 'string' as const },
      provider: { type: 'string' as const },
      observedAt: { type: 'string' as const, required: true as const },
      state: { type: 'string' as const, required: true as const, enum: [...PROVIDER_STATES] },
      executionEnabled: { type: 'boolean' as const, required: true as const, const: false },
      source: { type: 'string' as const, required: true as const },
      payload: { type: 'json' as const, required: true as const },
    },
  }
}

function renderDocument(value: {
  kind: OptionsDocument['kind']
  underlying?: string
  provider?: string
  observedAt: string
  state: OptionsDocument['state']
  executionEnabled: false
  source: string
}): string {
  const instrument = value.underlying ? ` ${value.underlying}` : ''
  const provider = value.provider ? ` via ${value.provider}` : ''
  return `${value.kind}${instrument} options research${provider} as of ${value.observedAt}: ${value.state}. Execution disabled.`
}

function chainTool(ctx: Context) {
  return defineTool({
    name: 'options_chain',
    description: 'Read a PureGamma Harness options chain with provider status, provenance and freshness. Read-only; this tool cannot submit orders.',
    parameters: {
      underlying: { type: 'string', required: true, description: 'Underlying symbol, for example BTC, ETH, AAPL or NVDA.' },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgOptions.chain(args.underlying)
    },
    presentCall: args => ({ card: 'generic', title: 'Read options chain', kind: 'other', rawInput: args.underlying }),
  })
}

function longGammaTool(ctx: Context) {
  return defineTool({
    name: 'options_long_gamma',
    description: 'Read research-ranked long-gamma option candidates. Scores include convexity, liquidity, spread, tenor and theta cost; execution remains disabled.',
    parameters: {
      underlying: { type: 'string', required: true, description: 'Underlying symbol.' },
      limit: { type: 'integer', description: 'Maximum candidates, 1-25. Defaults to 10.', default: 10 },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgOptions.longGamma(args.underlying, args.limit ?? 10)
    },
    presentCall: args => ({ card: 'generic', title: 'Read long-gamma candidates', kind: 'other', rawInput: `${args.underlying}:${args.limit ?? 10}` }),
  })
}

function surfaceTool(ctx: Context) {
  return defineTool({
    name: 'options_surface',
    description: 'Read the options surface and ATM/skew research snapshot for a supported metric. Read-only; unavailable providers return degraded/empty data rather than fabricated values.',
    parameters: {
      underlying: { type: 'string', required: true, description: 'Underlying symbol.' },
      type: { type: 'string', enum: [...SURFACE_TYPES], description: 'Surface metric. Defaults to mark_iv.', default: 'mark_iv' },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgOptions.surface(args.underlying, (args.type ?? 'mark_iv') as OptionsSurfaceType)
    },
    presentCall: args => ({ card: 'generic', title: 'Read options surface', kind: 'other', rawInput: `${args.underlying}:${args.type ?? 'mark_iv'}` }),
  })
}

function surfaceTickersTool(ctx: Context) {
  return defineTool({
    name: 'options_surface_tickers',
    description: 'Read the current catalog of underlyings supported by the PureGamma Harness options surface capability.',
    parameters: {},
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      return ctx.pgOptions.surfaceTickers()
    },
    presentCall: () => ({ card: 'generic', title: 'Read options surface tickers', kind: 'other', rawInput: '' }),
  })
}

function earningsGammaTool(ctx: Context) {
  return defineTool({
    name: 'options_earnings_gamma',
    description: 'Read earnings-related gamma research candidates. Migration filtering removes placeholder candidates without a verified earnings date and marks the document degraded when that occurs.',
    parameters: {
      language: { type: 'string', enum: ['en', 'zh'], description: 'Research language. Defaults to en.', default: 'en' },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgOptions.earningsGamma(args.language ?? 'en')
    },
    presentCall: args => ({ card: 'generic', title: 'Read earnings gamma research', kind: 'other', rawInput: args.language ?? 'en' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(chainTool(ctx))
  ctx.tools.register(longGammaTool(ctx))
  ctx.tools.register(surfaceTool(ctx))
  ctx.tools.register(surfaceTickersTool(ctx))
  ctx.tools.register(earningsGammaTool(ctx))
}
