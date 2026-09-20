import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-admin'

export const name = 'puregamma-tool-admin'
export const inject = ['tools', 'pgAdmin']

export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'admin_health',
    description: 'Read PureGamma business operations overview, system status and LLM provider status. This is read-only and does not alter users, credits, providers, plugins, trading or billing state.',
    parameters: {},
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {
        overview: { type: 'json', required: true },
        system: { type: 'json', required: true },
        llm: { type: 'json', required: true },
        observedAt: { type: 'string', required: true },
      } },
      render: (_args, value) => [{ type: 'text', text: `Admin health read at ${value.observedAt}.` }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      const [overview, system, llm] = await Promise.all([ctx.pgAdmin.overview(), ctx.pgAdmin.systemStatus(), ctx.pgAdmin.llmStatus()])
      return { overview: overview.payload, system: system.payload, llm: llm.payload, observedAt: new Date().toISOString() }
    },
    presentCall: () => ({ card: 'generic', title: 'Read admin health', kind: 'other' }),
  }))
}
