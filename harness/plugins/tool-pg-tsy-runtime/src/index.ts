import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-pg-tsy-runtime'

export const name = 'puregamma-tool-pg-tsy-runtime'
export const inject = ['tools', 'pgTsyRuntime']

function runtimeStatusTool(ctx: Context) {
  return defineTool({
    name: 'quant_runtime_status',
    description: 'Read the current PureGamma Harness quantitative trading runtime status from pg-tsy-core. This is read-only and includes readiness, lease, feed, order and startup-gate state.',
    parameters: {
      readiness: {
        type: 'boolean',
        description: 'When true, query readiness rather than process health. Readiness may be false while startup/reconcile gates are still blocking.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          processHealthy: { type: 'boolean', required: true },
          ready: { type: 'boolean', required: true },
          mode: { type: 'string', required: true, enum: ['shadow', 'paper', 'live', 'unknown'] },
          leaseHealthy: { type: 'boolean', required: true },
          feedsTotal: { type: 'integer', required: true },
          feedsConnected: { type: 'integer', required: true },
          eventsTotal: { type: 'integer', required: true },
          policyDecisionsTotal: { type: 'integer', required: true },
          openOrders: { type: 'integer', required: true },
          ordersJournaledTotal: { type: 'integer', required: true },
          blockingGates: { type: 'array', required: true, items: { type: 'string' } },
          lastError: { type: 'string' },
          observedAt: { type: 'string', required: true },
          source: { type: 'string', required: true },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: [
          `Quant runtime: ${value.mode} · ${value.ready ? 'ready' : 'not ready'} · process ${value.processHealthy ? 'healthy' : 'unhealthy'}`,
          `Feeds ${value.feedsConnected}/${value.feedsTotal} · lease ${value.leaseHealthy ? 'healthy' : 'unhealthy'} · open orders ${value.openOrders}`,
          value.blockingGates.length === 0 ? 'Blocking gates: none' : `Blocking gates: ${value.blockingGates.join(', ')}`,
          ...(value.lastError ? [`Last error: ${value.lastError}`] : []),
        ].join('\n'),
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const snapshot = args.readiness === true
        ? await ctx.pgTsyRuntime.ready()
        : await ctx.pgTsyRuntime.health()
      return {
        processHealthy: snapshot.processHealthy,
        ready: snapshot.ready,
        mode: snapshot.mode,
        leaseHealthy: snapshot.leaseHealthy,
        feedsTotal: snapshot.feedsTotal,
        feedsConnected: snapshot.feedsConnected,
        eventsTotal: snapshot.eventsTotal,
        policyDecisionsTotal: snapshot.policyDecisionsTotal,
        openOrders: snapshot.openOrders,
        ordersJournaledTotal: snapshot.ordersJournaledTotal,
        blockingGates: [...snapshot.blockingGates],
        ...(snapshot.lastError === undefined ? {} : { lastError: snapshot.lastError }),
        observedAt: snapshot.observedAt,
        source: snapshot.source,
      }
    },
    presentCall: args => ({
      card: 'generic',
      title: args.readiness === true ? 'Check quant runtime readiness' : 'Check quant runtime health',
      kind: 'other',
      rawInput: args,
    }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(runtimeStatusTool(ctx))
}
