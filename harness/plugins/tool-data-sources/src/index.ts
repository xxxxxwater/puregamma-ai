import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-data-sources'

export const name = 'puregamma-tool-data-sources'
export const inject = ['tools', 'pgDataSources']

const documentSchema = {
  type: 'object' as const, additionalProperties: false, properties: {
    kind: { type: 'string' as const, required: true as const },
    observedAt: { type: 'string' as const, required: true as const },
    source: { type: 'string' as const, required: true as const },
    payload: { type: 'json' as const, required: true as const },
  },
}

function catalogTool(ctx: Context) {
  return defineTool({
    name: 'data_source_catalog',
    description: 'Read the configured PureGamma data-source catalog and provider states. This does not enable providers, change credentials or trigger ingestion.',
    parameters: {},
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Data-source catalog read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: () => ctx.pgDataSources.catalog(),
    presentCall: () => ({ card: 'generic', title: 'Read data sources', kind: 'other' }),
  })
}

function statusTool(ctx: Context) {
  return defineTool({
    name: 'data_source_status',
    description: 'Read current PureGamma ingestion and research source health. Errors and degraded states are returned explicitly; this tool does not run config checks or sync jobs.',
    parameters: {},
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Data-source health read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: () => ctx.pgDataSources.health(),
    presentCall: () => ({ card: 'generic', title: 'Read data-source health', kind: 'other' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(catalogTool(ctx))
  ctx.tools.register(statusTool(ctx))
}
