import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-research-runner'

export const name = 'puregamma-tool-research-runner'
export const inject = ['tools', 'pgResearchSandbox']

const runSchema = {
  type: 'object' as const,
  additionalProperties: false,
  properties: {
    kind: { type: 'string' as const, required: true as const, const: 'run' },
    observedAt: { type: 'string' as const, required: true as const },
    source: { type: 'string' as const, required: true as const },
    payload: { type: 'json' as const, required: true as const },
  },
}

function runTool(ctx: Context) {
  return defineTool({
    name: 'research_code_run',
    description: 'Queue Python research code in the isolated PureGamma research sandbox. Code is validated and executes in the worker/container boundary, never inside the Harness host process.',
    parameters: {
      code: { type: 'string', required: true },
      datasetRefs: { type: 'array', items: { type: 'string' }, default: [] },
      limits: { type: 'json', required: true, description: 'Sandbox resource limits object. Server policy remains authoritative.' },
      idempotencyKey: { type: 'string', description: 'Optional stable request key; reuse it when retrying the same logical run.' },
    },
    output: { schema: runSchema, render: (_args, value) => [{ type: 'text', text: `Research sandbox run queued/read at ${value.observedAt}.` }] },
    async execute(args) {
      if (args.datasetRefs.length > 8) throw new Error('research_code_run: at most 8 dataset refs are allowed')
      if (typeof args.limits !== 'object' || args.limits === null || Array.isArray(args.limits)) throw new Error('research_code_run: limits must be a JSON object')
      return ctx.pgResearchSandbox.createRun({
        code: args.code,
        datasetRefs: args.datasetRefs,
        limits: args.limits,
        ...(args.idempotencyKey === undefined ? {} : { idempotencyKey: args.idempotencyKey }),
      })
    },
    presentCall: args => ({ card: 'generic', title: 'Run isolated research code', kind: 'other', rawInput: { datasetRefs: args.datasetRefs, hasIdempotencyKey: Boolean(args.idempotencyKey) } }),
  })
}

function statusTool(ctx: Context) {
  return defineTool({
    name: 'research_code_status',
    description: 'Read status, bounded log tail, metrics and figure metadata for a user-owned isolated research run.',
    parameters: { runId: { type: 'string', required: true } },
    output: { schema: runSchema, render: (_args, value) => [{ type: 'text', text: `Research sandbox status read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: args => ctx.pgResearchSandbox.getRun(args.runId),
    presentCall: args => ({ card: 'generic', title: 'Read research run', kind: 'other', rawInput: args.runId }),
  })
}

function cancelTool(ctx: Context) {
  return defineTool({
    name: 'research_code_cancel',
    description: 'Cancel a user-owned queued/running isolated research job. This reduces work and cannot submit trades or widen sandbox permissions.',
    parameters: { runId: { type: 'string', required: true } },
    output: { schema: runSchema, render: (_args, value) => [{ type: 'text', text: `Research sandbox cancel state returned at ${value.observedAt}.` }] },
    execute: args => ctx.pgResearchSandbox.cancelRun(args.runId),
    presentCall: args => ({ card: 'generic', title: 'Cancel research run', kind: 'other', rawInput: args.runId }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(runTool(ctx))
  ctx.tools.register(statusTool(ctx))
  ctx.tools.register(cancelTool(ctx))
}
