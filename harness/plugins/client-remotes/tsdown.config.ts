import { externalClientBundle } from '../../tsdown.client-external.ts'

export default externalClientBundle('@puregamma/dsh-client-remotes', {
  externals: ['@deepseek-ai/dsh-api-gateway'],
})
