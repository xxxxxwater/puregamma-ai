import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { BacktestDocument, BacktestJson } from '@puregamma/dsh-backtest'
import type {} from '@puregamma/dsh-backtest'

export const name = 'puregamma-tool-backtest'
export const inject = ['tools', 'pgBacktest']

const DOCUMENT_KINDS = ['status', 'spec', 'run', 'runs', 'artifact', 'strategy', 'data-status'] as const

function documentSchema() {
  return {
    type: 'object' as const,
    additionalProperties: false,
    properties: {
      kind: { type: 'string' as const, required: true as const, enum: [...DOCUMENT_KINDS] },
      observedAt: { type: 'string' as const, required: true as const },
      source: { type: 'string' as const, required: true as const },
      payload: { type: 'json' as const, required: true as const },
    },
  }
}

function renderDocument(value: Pick<BacktestDocument, 'kind' | 'observedAt' | 'source'>): string {
  return `${value.kind} backtest document as of ${value.observedAt} from ${value.source}.`
}

function objectJson(value: unknown, label: string): { [key: string]: BacktestJson } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error(`${label} must be a JSON object`)
  return value as { [key: string]: BacktestJson }
}

function statusTool(ctx: Context) {
  return defineTool({
    name: 'backtest_status',
    description: 'Read Backtest Lab engine/data status and supported symbols. Read-only.',
    parameters: {},
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => true,
    execute: async () => ctx.pgBacktest.status(),
    presentCall: () => ({ card: 'generic', title: 'Read backtest status', kind: 'other', rawInput: '' }),
  })
}

function compileTool(ctx: Context) {
  return defineTool({
    name: 'backtest_compile',
    description: 'Compile a natural-language strategy idea into a Backtest Lab specification. This does not start a billable backtest run.',
    parameters: {
      idea: { type: 'string', required: true, description: 'Strategy idea, up to 2000 characters.' },
      useMemory: { type: 'boolean', description: 'Whether the compiler may use the installed memory capability.', default: true },
      locale: { type: 'string', enum: ['en', 'zh'], description: 'Output locale.', default: 'en' },
    },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => true,
    execute: async args => ctx.pgBacktest.compile({ idea: args.idea, useMemory: args.useMemory ?? true, locale: args.locale ?? 'en' }),
    presentCall: args => ({ card: 'generic', title: 'Compile backtest spec', kind: 'other', rawInput: args.idea }),
  })
}

function runTool(ctx: Context) {
  return defineTool({
    name: 'backtest_run',
    description: 'Create and dispatch a backtest from a compiled JSON spec. May consume plan credits; provider-side entitlement and credit gates remain authoritative. An idempotency key is required.',
    parameters: {
      spec: { type: 'json', required: true, description: 'Compiled backtest specification object.' },
      windowDays: { type: 'integer', description: 'Historical window in days, 1-30.', default: 30 },
      idempotencyKey: { type: 'string', required: true, description: 'Stable unique key for safe retries; max 120 characters.' },
    },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => false,
    execute: async args => ctx.pgBacktest.run({
      spec: objectJson(args.spec, 'spec'),
      windowDays: args.windowDays ?? 30,
      idempotencyKey: args.idempotencyKey,
    }),
    presentCall: args => ({ card: 'generic', title: 'Run backtest', kind: 'other', rawInput: args.idempotencyKey }),
  })
}

function runsTool(ctx: Context) {
  return defineTool({
    name: 'backtest_runs',
    description: 'List authenticated backtest runs, including legacy and unified Backtest Lab runs.',
    parameters: {
      limit: { type: 'integer', description: 'Maximum rows, 1-50.', default: 20 },
      offset: { type: 'integer', description: 'Non-negative pagination offset.', default: 0 },
    },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => true,
    execute: async args => ctx.pgBacktest.listRuns({ limit: args.limit ?? 20, offset: args.offset ?? 0 }),
    presentCall: args => ({ card: 'generic', title: 'List backtests', kind: 'other', rawInput: `${args.limit ?? 20}:${args.offset ?? 0}` }),
  })
}

function resultTool(ctx: Context) {
  return defineTool({
    name: 'backtest_result',
    description: 'Read one authenticated backtest run with metrics, charts, trades, positions, errors and artifact descriptors.',
    parameters: { runId: { type: 'string', required: true, description: 'Backtest run id.' } },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => true,
    execute: async args => ctx.pgBacktest.result(args.runId),
    presentCall: args => ({ card: 'generic', title: 'Read backtest result', kind: 'other', rawInput: args.runId }),
  })
}

function cancelTool(ctx: Context) {
  return defineTool({
    name: 'backtest_cancel',
    description: 'Cancel an authenticated backtest run when its current state allows cancellation.',
    parameters: { runId: { type: 'string', required: true, description: 'Backtest run id.' } },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => false,
    execute: async args => ctx.pgBacktest.cancel(args.runId),
    presentCall: args => ({ card: 'generic', title: 'Cancel backtest', kind: 'other', rawInput: args.runId }),
  })
}

function exportTool(ctx: Context) {
  return defineTool({
    name: 'backtest_export',
    description: 'Create a JSON or CSV backtest export artifact. May consume credits according to the provider billing policy.',
    parameters: {
      runId: { type: 'string', required: true, description: 'Backtest run id.' },
      format: { type: 'string', enum: ['json', 'csv'], description: 'Export format.', default: 'json' },
    },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => false,
    execute: async args => ctx.pgBacktest.exportRun(args.runId, args.format ?? 'json'),
    presentCall: args => ({ card: 'generic', title: 'Export backtest', kind: 'other', rawInput: `${args.runId}:${args.format ?? 'json'}` }),
  })
}

function saveStrategyTool(ctx: Context) {
  return defineTool({
    name: 'backtest_save_strategy',
    description: 'Save a completed authenticated backtest run as a strategy record. This does not enable live trading.',
    parameters: { runId: { type: 'string', required: true, description: 'Backtest run id.' } },
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => false,
    execute: async args => ctx.pgBacktest.saveAsStrategy(args.runId),
    presentCall: args => ({ card: 'generic', title: 'Save backtest strategy', kind: 'other', rawInput: args.runId }),
  })
}

function refreshDataTool(ctx: Context) {
  return defineTool({
    name: 'backtest_refresh_data',
    description: 'Refresh Backtest Lab daily candle data through the configured data provider, then return data status. This is stateful but does not trade.',
    parameters: {},
    output: { schema: documentSchema(), render: (_args, value) => [{ type: 'text', text: renderDocument(value) }] },
    isConcurrencySafe: () => false,
    execute: async () => ctx.pgBacktest.refreshData(),
    presentCall: () => ({ card: 'generic', title: 'Refresh backtest data', kind: 'other', rawInput: '' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(statusTool(ctx))
  ctx.tools.register(compileTool(ctx))
  ctx.tools.register(runTool(ctx))
  ctx.tools.register(runsTool(ctx))
  ctx.tools.register(resultTool(ctx))
  ctx.tools.register(cancelTool(ctx))
  ctx.tools.register(exportTool(ctx))
  ctx.tools.register(saveStrategyTool(ctx))
  ctx.tools.register(refreshDataTool(ctx))
}
