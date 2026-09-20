import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-portfolio'

export const name = 'puregamma-tool-portfolio'
export const inject = ['tools', 'pgPortfolio']

const SIDE_VALUES = ['long', 'short', 'flat'] as const

function normalizeAccountIds(values: readonly string[]): string[] {
  return values.map(value => value.trim()).filter(Boolean)
}

function portfolioSnapshotTool(ctx: Context) {
  return defineTool({
    name: 'portfolio_snapshot',
    description: 'Read the current server-authoritative PureGamma Harness portfolio snapshot, including accounts, cash, positions, NAV and freshness state.',
    parameters: {
      accountIds: {
        type: 'array',
        required: true,
        items: { type: 'string' },
        description: 'Optional account filter. Pass an empty array for all connected accounts.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          observedAt: { type: 'string', required: true },
          available: { type: 'boolean', required: true },
          stale: { type: 'boolean', required: true },
          nav: { type: 'string' },
          cash: { type: 'string' },
          currency: { type: 'string', required: true },
          reason: { type: 'string' },
          accounts: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                id: { type: 'string', required: true },
                provider: { type: 'string', required: true },
                label: { type: 'string' },
                status: { type: 'string' },
                observedAt: { type: 'string' },
                stale: { type: 'boolean' },
              },
            },
          },
          positions: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                accountId: { type: 'string' },
                instrument: { type: 'string', required: true },
                side: { type: 'string', enum: [...SIDE_VALUES] },
                quantity: { type: 'string', required: true },
                markPrice: { type: 'string' },
                unrealizedPnl: { type: 'string' },
                source: { type: 'string', required: true },
                observedAt: { type: 'string', required: true },
                stale: { type: 'boolean', required: true },
              },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.available
          ? `Portfolio as of ${value.observedAt}: NAV ${value.nav ?? 'n/a'} ${value.currency}, cash ${value.cash ?? 'n/a'}, ${value.positions.length} positions${value.stale ? ' (stale)' : ''}.`
          : `Portfolio unavailable as of ${value.observedAt}: ${value.reason ?? 'no connected portfolio snapshot'}.`,
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const snapshot = await ctx.pgPortfolio.snapshot({ accountIds: normalizeAccountIds(args.accountIds) })
      return {
        observedAt: snapshot.observedAt,
        available: snapshot.nav.nav !== null,
        stale: snapshot.nav.stale,
        ...(snapshot.nav.nav === null ? {} : { nav: snapshot.nav.nav }),
        ...(snapshot.nav.cash === null ? {} : { cash: snapshot.nav.cash }),
        currency: snapshot.nav.currency,
        ...(snapshot.nav.reason === undefined ? {} : { reason: snapshot.nav.reason }),
        accounts: snapshot.accounts.map(account => ({
          id: account.id,
          provider: account.provider,
          ...(account.label === undefined ? {} : { label: account.label }),
          ...(account.status === undefined ? {} : { status: account.status }),
          ...(account.observedAt === undefined ? {} : { observedAt: account.observedAt }),
          ...(account.stale === undefined ? {} : { stale: account.stale }),
        })),
        positions: snapshot.positions.map(position => ({
          ...(position.accountId === undefined ? {} : { accountId: position.accountId }),
          instrument: position.instrument,
          ...(position.side === undefined ? {} : { side: position.side }),
          quantity: position.quantity,
          ...(position.markPrice === undefined ? {} : { markPrice: position.markPrice }),
          ...(position.unrealizedPnl === undefined ? {} : { unrealizedPnl: position.unrealizedPnl }),
          source: position.source,
          observedAt: position.observedAt,
          stale: position.stale,
        })),
      }
    },
    presentCall: args => ({ card: 'generic', title: 'Read portfolio snapshot', kind: 'other', rawInput: args.accountIds }),
  })
}

function portfolioPositionsTool(ctx: Context) {
  return defineTool({
    name: 'portfolio_positions',
    description: 'Read normalized portfolio positions with source and freshness metadata. Quantities and monetary values are decimal strings.',
    parameters: {
      accountIds: {
        type: 'array',
        required: true,
        items: { type: 'string' },
        description: 'Optional account filter. Pass an empty array for all connected accounts.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          positions: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                accountId: { type: 'string' },
                instrument: { type: 'string', required: true },
                side: { type: 'string', enum: [...SIDE_VALUES] },
                quantity: { type: 'string', required: true },
                markPrice: { type: 'string' },
                marketValue: { type: 'string' },
                unrealizedPnl: { type: 'string' },
                currency: { type: 'string', required: true },
                observedAt: { type: 'string', required: true },
                source: { type: 'string', required: true },
                stale: { type: 'boolean', required: true },
              },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.positions.length === 0
          ? 'No portfolio positions.'
          : value.positions.map(position => `${position.instrument}: ${position.side ?? ''} ${position.quantity}${position.markPrice ? ` @ ${position.markPrice}` : ''}${position.stale ? ' (stale)' : ''}`).join('\n'),
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const positions = await ctx.pgPortfolio.positions(normalizeAccountIds(args.accountIds))
      return {
        positions: positions.map(position => ({
          ...(position.accountId === undefined ? {} : { accountId: position.accountId }),
          instrument: position.instrument,
          ...(position.side === undefined ? {} : { side: position.side }),
          quantity: position.quantity,
          ...(position.markPrice === undefined ? {} : { markPrice: position.markPrice }),
          ...(position.marketValue === undefined ? {} : { marketValue: position.marketValue }),
          ...(position.unrealizedPnl === undefined ? {} : { unrealizedPnl: position.unrealizedPnl }),
          currency: position.currency,
          observedAt: position.observedAt,
          source: position.source,
          stale: position.stale,
        })),
      }
    },
    presentCall: args => ({ card: 'generic', title: 'Read portfolio positions', kind: 'other', rawInput: args.accountIds }),
  })
}

function portfolioNavTool(ctx: Context) {
  return defineTool({
    name: 'portfolio_nav',
    description: 'Read consolidated portfolio NAV/cash with explicit availability and freshness. Does not silently trigger billable vendor refreshes.',
    parameters: {
      accountIds: {
        type: 'array',
        required: true,
        items: { type: 'string' },
        description: 'Optional account filter. Pass an empty array for all connected accounts.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          available: { type: 'boolean', required: true },
          currency: { type: 'string', required: true },
          nav: { type: 'string' },
          cash: { type: 'string' },
          positionsValue: { type: 'string' },
          calculatedAt: { type: 'string', required: true },
          priceObservedAt: { type: 'string' },
          calculationVersion: { type: 'string', required: true },
          stale: { type: 'boolean', required: true },
          reason: { type: 'string' },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.available
          ? `NAV ${value.nav} ${value.currency}; cash ${value.cash ?? 'n/a'}; calculated ${value.calculatedAt}${value.stale ? ' (stale)' : ''}.`
          : `NAV unavailable: ${value.reason ?? 'no connected portfolio snapshot'}.`,
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const nav = await ctx.pgPortfolio.nav({ accountIds: normalizeAccountIds(args.accountIds) })
      return {
        available: nav.nav !== null,
        currency: nav.currency,
        ...(nav.nav === null ? {} : { nav: nav.nav }),
        ...(nav.cash === null ? {} : { cash: nav.cash }),
        ...(nav.positionsValue === null ? {} : { positionsValue: nav.positionsValue }),
        calculatedAt: nav.calculatedAt,
        ...(nav.priceObservedAt === undefined ? {} : { priceObservedAt: nav.priceObservedAt }),
        calculationVersion: nav.calculationVersion,
        stale: nav.stale,
        ...(nav.reason === undefined ? {} : { reason: nav.reason }),
      }
    },
    presentCall: args => ({ card: 'generic', title: 'Read portfolio NAV', kind: 'other', rawInput: args.accountIds }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(portfolioSnapshotTool(ctx))
  ctx.tools.register(portfolioPositionsTool(ctx))
  ctx.tools.register(portfolioNavTool(ctx))
}
