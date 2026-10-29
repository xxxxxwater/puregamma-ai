import { Context } from '@deepseek-ai/cordis'
import LegacyApiMarketDataProvider from '../../plugins/market-data-legacy-api/src/index.ts'
import LegacyApiPortfolioProvider from '../../plugins/portfolio-legacy-api/src/index.ts'
import { apply as applyMarketTools } from '../../plugins/tool-market-data/src/index.ts'
import { apply as applyPortfolioTools } from '../../plugins/tool-portfolio/src/index.ts'

/**
 * Read market data and portfolio state exactly as a Harness Host would: the
 * real compatibility providers mounted in a Cordis Context, and the real
 * model-facing tools (execute + render + presentationMeta) on top of them.
 * Used by the golden-fixture parity test and by the live FastAPI parity run
 * (tests/harness/test_market_portfolio_parity.py).
 */
export async function mountHarness({ baseUrl, authTokenFile }) {
  const root = new Context()
  const config = { baseUrl, authTokenFile, authTokenCacheMs: 0, requestTimeoutMs: 5000 }
  const forks = [root.plugin(LegacyApiMarketDataProvider, config), root.plugin(LegacyApiPortfolioProvider, config)]
  await new Promise(resolve => setTimeout(resolve, 0))
  const pgMarketData = root.get('pgMarketData')
  const pgPortfolio = root.get('pgPortfolio')
  if (!pgMarketData || !pgPortfolio) throw new Error('compatibility providers did not mount')
  const tools = new Map()
  const registry = { register: tool => { tools.set(tool.name, tool); return () => tools.delete(tool.name) } }
  applyMarketTools({ tools: registry, pgMarketData })
  applyPortfolioTools({ tools: registry, pgPortfolio })
  const run = async (name, args) => {
    const tool = tools.get(name)
    const value = await tool.execute(args)
    const rendered = tool.output.render?.(args, value) ?? []
    return { value, text: rendered.map(part => part.text ?? '').join('\n'), meta: tool.output.presentationMeta?.(args, value) ?? null }
  }
  return {
    services: { pgMarketData, pgPortfolio },
    run,
    dispose: () => { for (const fork of forks) fork.dispose() },
    mounted: () => ({ pgMarketData: root.get('pgMarketData') !== undefined, pgPortfolio: root.get('pgPortfolio') !== undefined }),
  }
}

export async function readThroughHarness({ baseUrl, authTokenFile, accountIds = [] }) {
  const harness = await mountHarness({ baseUrl, authTokenFile })
  try {
    return {
      portfolioService: await harness.services.pgPortfolio.snapshot({ accountIds }),
      portfolioSnapshotTool: await harness.run('portfolio_snapshot', { accountIds }),
      portfolioNavTool: await harness.run('portfolio_nav', { accountIds }),
      portfolioPositionsTool: await harness.run('portfolio_positions', { accountIds }).catch(error => ({ error: error.message })),
      marketService: await harness.services.pgMarketData.snapshot([]),
      marketSnapshotTool: await harness.run('market_snapshot', { instruments: [] }),
    }
  } finally {
    harness.dispose()
  }
}

// CLI for the live run: `tsx harness-reads.mjs <baseUrl> <tokenFile> [accountId...]` prints JSON.
if (import.meta.url === `file://${process.argv[1]}`) {
  const [baseUrl, authTokenFile, ...accountIds] = process.argv.slice(2)
  process.stdout.write(JSON.stringify(await readThroughHarness({ baseUrl, authTokenFile, accountIds })))
}
