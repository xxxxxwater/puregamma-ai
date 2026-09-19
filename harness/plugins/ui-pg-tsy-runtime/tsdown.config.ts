import { externalClientBundle } from '../../tsdown.client-external.ts'

export default externalClientBundle('@puregamma/dsh-ui-pg-tsy-runtime', {
  externals: [
    '@deepseek-ai/dsh-api-gateway',
    '@deepseek-ai/dsh-client-resources',
    '@deepseek-ai/dsh-client-locale',
    '@deepseek-ai/dsh-client-ui-settings',
    '@puregamma/dsh-client-remotes',
  ],
})
