import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-api-gateway'

export const name = 'puregamma-tool-api-gateway'
export const inject = ['tools', 'pgModelGateway']

const documentSchema = {
  type: 'object' as const, additionalProperties: false, properties: {
    kind: { type: 'string' as const, required: true as const },
    observedAt: { type: 'string' as const, required: true as const },
    source: { type: 'string' as const, required: true as const },
    payload: { type: 'json' as const, required: true as const },
  },
}

function modelsTool(ctx: Context) {
  return defineTool({
    name: 'gateway_models',
    description: 'Read the PureGamma API Gateway public model catalog, reviewed prices and availability. This never calls a model or changes provider routing.',
    parameters: {},
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Gateway catalog read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: () => ctx.pgModelGateway.catalog(),
    presentCall: () => ({ card: 'generic', title: 'Read Gateway models', kind: 'other' }),
  })
}

function usageTool(ctx: Context) {
  return defineTool({
    name: 'gateway_usage',
    description: 'Read the current user\'s metered PureGamma Gateway usage. This cannot top up wallet balance, change spend limits or alter pricing.',
    parameters: {
      start: { type: 'string' },
      end: { type: 'string' },
      granularity: { type: 'string', enum: ['hour', 'day'], default: 'day' },
      model: { type: 'string' },
      apiKeyId: { type: 'string' },
    },
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Gateway usage read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: args => ctx.pgModelGateway.usage({
      ...(args.start ? { start: args.start } : {}),
      ...(args.end ? { end: args.end } : {}),
      granularity: args.granularity === 'hour' ? 'hour' : 'day',
      ...(args.model ? { model: args.model } : {}),
      ...(args.apiKeyId ? { apiKeyId: args.apiKeyId } : {}),
    }),
    presentCall: args => ({ card: 'generic', title: 'Read Gateway usage', kind: 'other', rawInput: { granularity: args.granularity, model: args.model } }),
  })
}

function keysTool(ctx: Context) {
  return defineTool({
    name: 'gateway_keys',
    description: 'List metadata for the current user\'s PureGamma Gateway API keys. Raw key secrets are never returned by this tool, and it cannot create, rotate, pause or revoke keys.',
    parameters: {},
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Gateway key metadata read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: () => ctx.pgModelGateway.keys(),
    presentCall: () => ({ card: 'generic', title: 'Read Gateway keys', kind: 'other' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(modelsTool(ctx))
  ctx.tools.register(usageTool(ctx))
  ctx.tools.register(keysTool(ctx))
}
