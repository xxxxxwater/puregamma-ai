import { nodePlugin } from '../../tsdown.node.ts'

export default { ...nodePlugin(), entry: ['src/index.ts', 'src/policy.ts'] }
