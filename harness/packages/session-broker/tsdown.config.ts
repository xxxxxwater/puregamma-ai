import { nodePlugin } from '../../tsdown.node.ts'

const base = nodePlugin()
export default { ...base, entry: ['src/index.ts', 'src/main.ts'] }
