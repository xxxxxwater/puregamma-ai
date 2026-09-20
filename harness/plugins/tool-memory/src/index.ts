import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { MemoryDocument } from '@puregamma/dsh-memory'
import type {} from '@puregamma/dsh-memory'

export const name = 'puregamma-tool-memory'
export const inject = ['tools', 'pgMemory']

const DOCUMENT_KINDS = ['settings', 'items', 'proposals', 'proposal', 'mutation', 'export'] as const

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

function renderDocument(value: Pick<MemoryDocument, 'kind' | 'observedAt' | 'source'>): string {
  return `${value.kind} memory document as of ${value.observedAt} from ${value.source}.`
}

function settingsTool(ctx: Context) {
  return defineTool({
    name: 'memory_settings',
    description: 'Read the authenticated user memory settings, consent requirement and retention policy. Read-only; this tool never grants consent or enables a scope.',
    parameters: {},
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    execute: async () => ctx.pgMemory.settings(),
    presentCall: () => ({ card: 'generic', title: 'Read memory settings', kind: 'other', rawInput: '' }),
  })
}

function itemsTool(ctx: Context) {
  return defineTool({
    name: 'memory_items',
    description: 'List the authenticated user memory items for a user-facing scope. Returned content is the server-redacted preview only. This listing is not permission to inject these rows into model context.',
    parameters: {
      scope: {
        type: 'string',
        enum: ['short_term', 'mid_term'],
        description: 'User-facing memory scope. Defaults to short_term.',
        default: 'short_term',
      },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    execute: async args => ctx.pgMemory.listItems(args.scope ?? 'short_term'),
    presentCall: args => ({ card: 'generic', title: 'List memory items', kind: 'other', rawInput: args.scope ?? 'short_term' }),
  })
}

function proposalsTool(ctx: Context) {
  return defineTool({
    name: 'memory_proposals',
    description: 'List memory proposals and their policy/user decision state. Read-only; approving or rejecting proposals remains an explicit user-controlled service/UI action.',
    parameters: {
      status: { type: 'string', description: 'Optional proposal status filter, for example pending or rejected.' },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    execute: async args => ctx.pgMemory.listProposals({
      ...(args.status === undefined || args.status.trim() === '' ? {} : { status: args.status }),
    }),
    presentCall: args => ({ card: 'generic', title: 'List memory proposals', kind: 'other', rawInput: args.status ?? '' }),
  })
}

function exportDescriptorTool(ctx: Context) {
  return defineTool({
    name: 'memory_export_descriptor',
    description: 'Request the authenticated user memory export descriptor. The raw export bytes remain a service/UI capability and are not injected into the model by this tool.',
    parameters: {},
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    execute: async () => ctx.pgMemory.exportDescriptor(),
    presentCall: () => ({ card: 'generic', title: 'Prepare memory export', kind: 'other', rawInput: '' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(settingsTool(ctx))
  ctx.tools.register(itemsTool(ctx))
  ctx.tools.register(proposalsTool(ctx))
  ctx.tools.register(exportDescriptorTool(ctx))
}
