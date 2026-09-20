import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-billing'

export const name = 'puregamma-tool-billing'
export const inject = ['tools', 'pgBilling']

const documentSchema = {
  type: 'object' as const, additionalProperties: false, properties: {
    kind: { type: 'string' as const, required: true as const },
    observedAt: { type: 'string' as const, required: true as const },
    source: { type: 'string' as const, required: true as const },
    payload: { type: 'json' as const, required: true as const },
  },
}

function statusTool(ctx: Context) {
  return defineTool({
    name: 'billing_status',
    description: 'Read PureGamma subscription, credit balance and plan entitlements. This cannot start checkout, change plans or cancel subscriptions.',
    parameters: {},
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {
        subscription: { type: 'json', required: true },
        credits: { type: 'json', required: true },
        entitlements: { type: 'json', required: true },
        observedAt: { type: 'string', required: true },
      } },
      render: (_args, value) => [{ type: 'text', text: `Billing status read at ${value.observedAt}.` }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      const [subscription, credits, entitlements] = await Promise.all([ctx.pgBilling.subscription(), ctx.pgBilling.credits(), ctx.pgBilling.entitlements()])
      return { subscription: subscription.payload, credits: credits.payload, entitlements: entitlements.payload, observedAt: new Date().toISOString() }
    },
    presentCall: () => ({ card: 'generic', title: 'Read billing status', kind: 'other' }),
  })
}

function quoteTool(ctx: Context) {
  return defineTool({
    name: 'billing_quote',
    description: 'Estimate PureGamma credits for a supported task using current entitlement-aware server pricing. Estimation does not reserve or spend credits.',
    parameters: {
      taskType: { type: 'string', default: 'default_chat' },
      requestedModel: { type: 'string', default: 'default' },
      inputTokens: { type: 'integer', default: 0 },
      outputTokens: { type: 'integer', default: 0 },
      attachmentBytes: { type: 'integer', default: 0 },
      toolCalls: { type: 'array', items: { type: 'string' }, default: [] },
      selectedDataSources: { type: 'array', items: { type: 'string' }, default: [] },
    },
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Billing quote returned at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: args => ctx.pgBilling.quote({
      taskType: args.taskType ?? 'default_chat',
      requestedModel: args.requestedModel ?? 'default',
      inputTokens: args.inputTokens ?? 0,
      outputTokens: args.outputTokens ?? 0,
      attachmentBytes: args.attachmentBytes ?? 0,
      toolCalls: args.toolCalls ?? [],
      selectedDataSources: args.selectedDataSources ?? [],
    }),
    presentCall: args => ({ card: 'generic', title: 'Estimate credits', kind: 'other', rawInput: { taskType: args.taskType, requestedModel: args.requestedModel } }),
  })
}

function budgetTool(ctx: Context) {
  return defineTool({
    name: 'billing_budget',
    description: 'Read current PureGamma automation credit budgets and pause state. This tool does not modify budgets.',
    parameters: {},
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Billing budgets read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: () => ctx.pgBilling.budget(),
    presentCall: () => ({ card: 'generic', title: 'Read automation budgets', kind: 'other' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(statusTool(ctx))
  ctx.tools.register(quoteTool(ctx))
  ctx.tools.register(budgetTool(ctx))
}
