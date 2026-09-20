import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-skills'

export const name = 'puregamma-tool-skills'
export const inject = ['tools', 'pgSkills']

const documentSchema = {
  type: 'object' as const,
  additionalProperties: false,
  properties: {
    kind: { type: 'string' as const, required: true as const, enum: ['catalog', 'runs', 'run'] },
    observedAt: { type: 'string' as const, required: true as const },
    source: { type: 'string' as const, required: true as const },
    payload: { type: 'json' as const, required: true as const },
  },
}

function skillCatalogTool(ctx: Context) {
  return defineTool({
    name: 'skill_catalog',
    description: 'List PureGamma skills visible to the current user through the installed policy-aware skill registry.',
    parameters: { includeDisabled: { type: 'boolean', default: false } },
    output: {
      schema: documentSchema,
      render: (_args, value) => [{ type: 'text', text: `Skill catalog loaded at ${value.observedAt} from ${value.source}.` }],
    },
    isConcurrencySafe: () => true,
    execute: args => ctx.pgSkills.catalog(args.includeDisabled ?? false),
    presentCall: args => ({ card: 'generic', title: 'Read skill catalog', kind: 'other', rawInput: args }),
  })
}

function skillRunTool(ctx: Context) {
  return defineTool({
    name: 'skill_run',
    description: 'Run an installed PureGamma workflow skill through server-side manifest, tool-allowlist, cost and permission policy. This tool cannot set allow_autopilot or allow_order_intent bypass flags.',
    parameters: {
      slug: { type: 'string', required: true },
      inputs: { type: 'json', required: true, description: 'Lossless JSON inputs for the installed skill.' },
      estimatedCredits: { type: 'integer', default: 0, description: 'Estimated credit budget, 0-10000.' },
    },
    output: {
      schema: documentSchema,
      render: (_args, value) => [{ type: 'text', text: `Skill run returned ${value.kind} state at ${value.observedAt}.` }],
    },
    async execute(args) {
      const credits = args.estimatedCredits ?? 0
      if (!Number.isInteger(credits) || credits < 0 || credits > 10000) throw new Error('skill_run: estimatedCredits must be 0-10000')
      if (typeof args.inputs !== 'object' || args.inputs === null || Array.isArray(args.inputs)) throw new Error('skill_run: inputs must be a JSON object')
      return ctx.pgSkills.run(args.slug, args.inputs, credits)
    },
    presentCall: args => ({ card: 'generic', title: 'Run installed skill', kind: 'other', rawInput: { slug: args.slug, estimatedCredits: args.estimatedCredits ?? 0 } }),
  })
}

function skillRunStatusTool(ctx: Context) {
  return defineTool({
    name: 'skill_run_status',
    description: 'Read one user-owned PureGamma skill run and its workflow evidence/status.',
    parameters: { runId: { type: 'string', required: true } },
    output: {
      schema: documentSchema,
      render: (_args, value) => [{ type: 'text', text: `Skill run status read at ${value.observedAt}.` }],
    },
    isConcurrencySafe: () => true,
    execute: args => ctx.pgSkills.runDetail(args.runId),
    presentCall: args => ({ card: 'generic', title: 'Read skill run', kind: 'other', rawInput: args.runId }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(skillCatalogTool(ctx))
  ctx.tools.register(skillRunTool(ctx))
  ctx.tools.register(skillRunStatusTool(ctx))
}
