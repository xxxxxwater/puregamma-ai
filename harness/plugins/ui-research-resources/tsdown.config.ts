import { externalClientBundle } from '../../tsdown.client-external.ts'

export default externalClientBundle('@puregamma/dsh-ui-research-resources', {
  externals: [
    '@deepseek-ai/dsh-api-gateway',
    '@deepseek-ai/dsh-client-resources',
    '@deepseek-ai/dsh-client-locale',
    '@deepseek-ai/dsh-client-ui-sidebar-right',
    '@puregamma/dsh-client-remotes',
  ],
})
