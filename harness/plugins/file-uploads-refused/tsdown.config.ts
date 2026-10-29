import { externalClientBundle } from '../../tsdown.client-external.ts'

// The Host half registers a Cordis Service, so it must share the Host's cordis.
export default externalClientBundle('@puregamma/dsh-file-uploads-refused', { hostExternals: ['@deepseek-ai/cordis'] })
