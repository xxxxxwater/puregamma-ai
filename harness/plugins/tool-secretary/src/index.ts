import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-secretary'

export const name = 'puregamma-tool-secretary'
export const inject = ['tools', 'pgSecretary']

function secretaryStatusTool(ctx: Context) {
  return defineTool({
    name: 'secretary_status',
    description: 'Read the installed PureGamma private-secretary capability status without exposing private message contents or performing state-changing actions.',
    parameters: {
      locale: { type: 'string', enum: ['zh', 'en'], default: 'zh', description: 'Voice/status locale.' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          conversationActive: { type: 'boolean', required: true },
          messageCount: { type: 'integer', required: true },
          voiceId: { type: 'string', required: true },
          voiceName: { type: 'string', required: true },
          voiceFixed: { type: 'boolean', required: true },
          memoryEnabled: { type: 'boolean', required: true },
          isolatedByUser: { type: 'boolean', required: true },
          creditsPerReply: { type: 'number', required: true },
          creditBalance: { type: 'number', required: true },
          skills: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                id: { type: 'string', required: true },
                status: { type: 'string', required: true },
                risk: { type: 'string', required: true },
              },
            },
          },
          observedAt: { type: 'string', required: true },
          source: { type: 'string', required: true },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: `Secretary: ${value.conversationActive ? 'active conversation' : 'no active conversation'}, ${value.messageCount} stored messages, voice ${value.voiceName}, memory ${value.memoryEnabled ? 'enabled' : 'disabled'}.`,
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const state = await ctx.pgSecretary.state(args.locale === 'en' ? 'en' : 'zh')
      return {
        conversationActive: Boolean(state.conversationId),
        messageCount: state.messages.length,
        voiceId: state.voice.id,
        voiceName: state.voice.name,
        voiceFixed: state.voice.fixed,
        memoryEnabled: state.memory.enabled,
        isolatedByUser: state.memory.isolatedByUser,
        creditsPerReply: state.billing.creditsPerReply,
        creditBalance: state.billing.creditBalance,
        skills: state.skills.map(item => ({ id: item.id, status: item.status, risk: item.risk })),
        observedAt: state.observedAt,
        source: state.source,
      }
    },
    presentCall: args => ({ card: 'generic', title: 'Check secretary status', kind: 'other', rawInput: args }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(secretaryStatusTool(ctx))
}
