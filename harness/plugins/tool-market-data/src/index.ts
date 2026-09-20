import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-market-data'

export const name = 'puregamma-tool-market-data'
export const inject = ['tools', 'pgMarketData']

const ASSET_CLASSES = ['crypto', 'equity', 'option', 'fx', 'rate', 'commodity'] as const

function marketSnapshotTool(ctx: Context) {
  return defineTool({
    name: 'market_snapshot',
    description: 'Read a timestamped PureGamma market snapshot from the installed market-data provider. Returned quotes always include source and stale state.',
    parameters: {
      instruments: {
        type: 'array',
        required: true,
        description: 'Instruments to read. Pass an empty array for the provider default universe.',
        items: {
          type: 'object',
          additionalProperties: false,
          properties: {
            symbol: { type: 'string', required: true },
            venue: { type: 'string', required: true },
            assetClass: { type: 'string', required: true, enum: [...ASSET_CLASSES] },
          },
        },
      },
      maxAgeMs: {
        type: 'integer',
        description: 'Optional maximum quote age in milliseconds. Providers mark older/non-realtime values stale instead of hiding them.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          asOf: { type: 'string', required: true },
          quotes: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                symbol: { type: 'string', required: true },
                venue: { type: 'string', required: true },
                assetClass: { type: 'string', required: true, enum: [...ASSET_CLASSES] },
                bid: { type: 'string' },
                ask: { type: 'string' },
                last: { type: 'string' },
                mark: { type: 'string' },
                volume24h: { type: 'string' },
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
        text: value.quotes.length === 0
          ? `Market snapshot ${value.asOf}: no matching instruments.`
          : [
              `Market snapshot as of ${value.asOf}:`,
              ...value.quotes.map(quote => {
                const spread = [quote.bid, quote.ask].filter(Boolean).join('/')
                const price = quote.last ?? quote.mark ?? spread
                return `${quote.symbol}: ${price || 'n/a'} (${quote.source}${quote.stale ? ', stale' : ''})`
              }),
            ].join('\n'),
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const maxAgeMs = args.maxAgeMs === undefined ? undefined : Number(args.maxAgeMs)
      if (maxAgeMs !== undefined && (!Number.isInteger(maxAgeMs) || maxAgeMs < 0)) {
        throw new Error('market_snapshot: maxAgeMs must be a non-negative integer')
      }
      const result = await ctx.pgMarketData.snapshot(args.instruments.map(item => ({
        symbol: item.symbol.trim().toUpperCase(),
        venue: item.venue.trim() || 'auto',
        assetClass: item.assetClass,
      })), maxAgeMs)
      return {
        asOf: result.asOf,
        quotes: result.quotes.map(quote => ({
          symbol: quote.instrument.symbol,
          venue: quote.instrument.venue,
          assetClass: quote.instrument.assetClass,
          ...(quote.bid === undefined ? {} : { bid: quote.bid }),
          ...(quote.ask === undefined ? {} : { ask: quote.ask }),
          ...(quote.last === undefined ? {} : { last: quote.last }),
          ...(quote.mark === undefined ? {} : { mark: quote.mark }),
          ...(quote.volume24h === undefined ? {} : { volume24h: quote.volume24h }),
          observedAt: quote.observedAt,
          source: quote.source,
          stale: quote.stale,
        })),
      }
    },
    presentCall: args => ({
      card: 'generic',
      title: 'Read market snapshot',
      kind: 'other',
      rawInput: args.instruments,
    }),
  })
}

function marketNewsTool(ctx: Context) {
  return defineTool({
    name: 'market_news',
    description: 'Read recent attributed market headlines from the installed PureGamma news provider. Fails explicitly when the user/provider is not entitled or authenticated.',
    parameters: {
      symbols: {
        type: 'array',
        required: true,
        items: { type: 'string' },
        description: 'Symbols to filter. Pass an empty array for an unfiltered feed.',
      },
      limit: { type: 'integer', description: 'Maximum number of items, 1-50.' },
      since: { type: 'string', description: 'Optional ISO-8601 lower time bound.' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          items: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                id: { type: 'string', required: true },
                source: { type: 'string', required: true },
                title: { type: 'string', required: true },
                summary: { type: 'string' },
                url: { type: 'string' },
                publishedAt: { type: 'string', required: true },
                symbols: { type: 'array', items: { type: 'string' } },
                language: { type: 'string' },
              },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.items.length === 0
          ? 'No matching market news.'
          : value.items.map(item => `${item.publishedAt} · ${item.source} · ${item.title}`).join('\n'),
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      const limit = args.limit === undefined ? undefined : Number(args.limit)
      if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 50)) {
        throw new Error('market_news: limit must be an integer from 1 to 50')
      }
      const items = await ctx.pgMarketData.news({
        symbols: args.symbols.map(symbol => symbol.trim().toUpperCase()).filter(Boolean),
        ...(limit === undefined ? {} : { limit }),
        ...(args.since === undefined || args.since.trim() === '' ? {} : { since: args.since }),
      })
      return {
        items: items.map(item => ({
          id: item.id,
          source: item.source,
          title: item.title,
          ...(item.summary === undefined ? {} : { summary: item.summary }),
          ...(item.url === undefined ? {} : { url: item.url }),
          publishedAt: item.publishedAt,
          ...(item.symbols === undefined ? {} : { symbols: [...item.symbols] }),
          ...(item.language === undefined ? {} : { language: item.language }),
        })),
      }
    },
    presentCall: args => ({ card: 'generic', title: 'Read market news', kind: 'other', rawInput: args }),
  })
}

function providerHealthTool(ctx: Context) {
  return defineTool({
    name: 'market_provider_health',
    description: 'Inspect the health of currently installed PureGamma market/news providers before relying on them.',
    parameters: {},
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          providers: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                provider: { type: 'string', required: true },
                state: { type: 'string', required: true, enum: ['starting', 'healthy', 'degraded', 'unavailable'] },
                observedAt: { type: 'string', required: true },
                detail: { type: 'string' },
              },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.providers.map(item => `${item.provider}: ${item.state}${item.detail ? ` (${item.detail})` : ''}`).join('\n'),
      }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      const providers = await ctx.pgMarketData.health()
      return {
        providers: providers.map(item => ({
          provider: item.provider,
          state: item.state,
          observedAt: item.observedAt,
          ...(item.detail === undefined ? {} : { detail: item.detail }),
        })),
      }
    },
    presentCall: () => ({ card: 'generic', title: 'Check market provider health', kind: 'other' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(marketSnapshotTool(ctx))
  ctx.tools.register(marketNewsTool(ctx))
  ctx.tools.register(providerHealthTool(ctx))
}
