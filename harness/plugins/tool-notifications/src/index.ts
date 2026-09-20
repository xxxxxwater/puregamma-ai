import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-notifications'

export const name = 'puregamma-tool-notifications'
export const inject = ['tools', 'pgNotifications']

const documentSchema = {
  type: 'object' as const, additionalProperties: false, properties: {
    kind: { type: 'string' as const, required: true as const },
    observedAt: { type: 'string' as const, required: true as const },
    source: { type: 'string' as const, required: true as const },
    payload: { type: 'json' as const, required: true as const },
  },
}

function channelsTool(ctx: Context) {
  return defineTool({
    name: 'notification_channels',
    description: 'Read configured PureGamma notification channel state (push devices and iMessage configuration). This tool never sends a message.',
    parameters: {},
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {
        devices: { type: 'json', required: true }, imessage: { type: 'json', required: true }, observedAt: { type: 'string', required: true },
      } },
      render: (_args, value) => [{ type: 'text', text: `Notification channel state read at ${value.observedAt}.` }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      const [devices, imessage] = await Promise.all([ctx.pgNotifications.devices(), ctx.pgNotifications.imessageConfig()])
      return { devices: devices.payload, imessage: imessage.payload, observedAt: new Date().toISOString() }
    },
    presentCall: () => ({ card: 'generic', title: 'Read notification channels', kind: 'other' }),
  })
}

function dailyBriefTool(ctx: Context) {
  return defineTool({
    name: 'notification_daily_brief',
    description: 'Read PureGamma daily-brief schedule, channels and recent delivery history. This tool does not modify the schedule.',
    parameters: {},
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Daily brief preference read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: () => ctx.pgNotifications.dailyBrief(),
    presentCall: () => ({ card: 'generic', title: 'Read daily brief preference', kind: 'other' }),
  })
}

function deliveriesTool(ctx: Context) {
  return defineTool({
    name: 'notification_deliveries',
    description: 'Read recent PureGamma notification delivery records. This tool does not retry or send deliveries.',
    parameters: { channel: { type: 'string', description: 'Optional channel filter.' } },
    output: { schema: documentSchema, render: (_args, value) => [{ type: 'text', text: `Notification delivery history read at ${value.observedAt}.` }] },
    isConcurrencySafe: () => true,
    execute: args => ctx.pgNotifications.deliveries(args.channel),
    presentCall: args => ({ card: 'generic', title: 'Read notification deliveries', kind: 'other', rawInput: args.channel ?? '' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(channelsTool(ctx))
  ctx.tools.register(dailyBriefTool(ctx))
  ctx.tools.register(deliveriesTool(ctx))
}
