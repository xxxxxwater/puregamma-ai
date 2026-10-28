import { externalClientBundle } from '../../tsdown.client-external.ts'

export default externalClientBundle('@puregamma/dsh-ui-backtest', {
  externals: ['@deepseek-ai/dsh-client-ui-tool', '@deepseek-ai/dsh-client-locale', '@deepseek-ai/dsh-client-ui-renderer'],
})
