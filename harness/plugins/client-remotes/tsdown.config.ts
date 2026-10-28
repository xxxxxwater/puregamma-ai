import { externalClientBundle } from '../../tsdown.client-external.ts'

export default externalClientBundle('@puregamma/dsh-client-remotes', {
  externals: ['@deepseek-ai/dsh-api-gateway'],
  // The Host half mounts PureGammaClientGateway, so it must use the Host's
  // Cordis/Typert classes and the workspace-built gateway package.
  hostExternals: ['@deepseek-ai/cordis', '@deepseek-ai/dsh-typert-protocol', '@puregamma/dsh-client-gateway'],
})
