import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ResearchDocument } from '@puregamma/dsh-research'
import type {} from '@puregamma/dsh-research'

export const name = 'puregamma-tool-research'
export const inject = ['tools', 'pgResearch']

const RESEARCH_KINDS = [
  'today',
  'overnight',
  'portfolio-impact',
  'upcoming-events',
  'opportunities',
  'alerts',
] as const

function documentSchema() {
  return {
    type: 'object' as const,
    additionalProperties: false,
    properties: {
      kind: { type: 'string' as const, required: true as const, enum: [...RESEARCH_KINDS] },
      asOf: { type: 'string' as const },
      observedAt: { type: 'string' as const, required: true as const },
      degraded: { type: 'boolean' as const, required: true as const },
      source: { type: 'string' as const, required: true as const },
      payload: { type: 'json' as const, required: true as const },
    },
  }
}

function renderDocument(value: {
  kind: ResearchDocument['kind']
  asOf?: string
  observedAt: string
  degraded: boolean
  source: string
}): string {
  const effectiveAt = value.asOf ?? value.observedAt
  return `${value.kind} research as of ${effectiveAt} from ${value.source}${value.degraded ? ' (degraded)' : ''}.`
}

function todayTool(ctx: Context) {
  return defineTool({
    name: 'research_today',
    description: 'Read PureGamma Harness daily research: what happened, portfolio impact, suggested next actions, next scheduled event and source health. Read-only and evidence-backed.',
    parameters: {
      locale: { type: 'string', description: 'Optional locale, for example en or zh-CN.' },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgResearch.today(args.locale)
    },
    presentCall: args => ({ card: 'generic', title: 'Read daily research', kind: 'other', rawInput: args.locale ?? '' }),
  })
}

function overnightTool(ctx: Context) {
  return defineTool({
    name: 'research_overnight',
    description: 'Read stored PureGamma Harness market events from the recent overnight window with evidence, impacts and provider health. Does not invent missing events.',
    parameters: {
      sinceHours: { type: 'integer', description: 'Lookback window in hours, 1-72. Defaults to 14.', default: 14 },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgResearch.overnight(args.sinceHours ?? 14)
    },
    presentCall: args => ({ card: 'generic', title: 'Read overnight research', kind: 'other', rawInput: String(args.sinceHours ?? 14) }),
  })
}

function portfolioImpactTool(ctx: Context) {
  return defineTool({
    name: 'research_portfolio_impact',
    description: 'Read research events currently linked to the authenticated portfolio through stored impact evidence. Users without real linked holdings are not fabricated into the result.',
    parameters: {},
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      return ctx.pgResearch.portfolioImpact()
    },
    presentCall: () => ({ card: 'generic', title: 'Read portfolio research impact', kind: 'other', rawInput: '' }),
  })
}

function upcomingEventsTool(ctx: Context) {
  return defineTool({
    name: 'research_upcoming_events',
    description: 'Read upcoming stored scheduled research events such as confirmed earnings and macro calendar events, with provenance and health metadata.',
    parameters: {
      days: { type: 'integer', description: 'Forward window in days, 1-60. Defaults to 14.', default: 14 },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgResearch.upcomingEvents(args.days ?? 14)
    },
    presentCall: args => ({ card: 'generic', title: 'Read upcoming research events', kind: 'other', rawInput: String(args.days ?? 14) }),
  })
}

function opportunitiesTool(ctx: Context) {
  return defineTool({
    name: 'research_opportunities',
    description: 'Read evidence-backed PureGamma Harness opportunity candidates, including available options context, confirmed earnings and recent price-move research. Execution is not enabled by this tool.',
    parameters: {
      locale: { type: 'string', description: 'Optional locale, for example en or zh-CN.' },
    },
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      return ctx.pgResearch.opportunities(args.locale)
    },
    presentCall: args => ({ card: 'generic', title: 'Read research opportunities', kind: 'other', rawInput: args.locale ?? '' }),
  })
}

function alertsTool(ctx: Context) {
  return defineTool({
    name: 'research_alerts',
    description: 'Read stored research alerts and delivery state for the authenticated user. This is read-only; it does not send or create notifications.',
    parameters: {},
    output: {
      schema: documentSchema(),
      render: (_args, value) => [{ type: 'text', text: renderDocument(value) }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      return ctx.pgResearch.alerts()
    },
    presentCall: () => ({ card: 'generic', title: 'Read research alerts', kind: 'other', rawInput: '' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(todayTool(ctx))
  ctx.tools.register(overnightTool(ctx))
  ctx.tools.register(portfolioImpactTool(ctx))
  ctx.tools.register(upcomingEventsTool(ctx))
  ctx.tools.register(opportunitiesTool(ctx))
  ctx.tools.register(alertsTool(ctx))
}
