import { defineConfig } from 'tsdown'
import { typertPlugin } from '@deepseek-ai/dsh-typert-generator/tsdown'

/**
 * PureGamma Host lib pass. TypeScript project references emit `lib/types`
 * first; this workspace pass consumes those JavaScript files and runs Typert
 * once against the Host aggregate so every Host Remote contribution is
 * generated before Client packages typecheck.
 */
export default defineConfig({
  // Only Typert Host packages; the session broker is a plain Node service.
  workspace: ['packages/client-gateway'],
  entry: ['lib/types/index.js'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  sourcemap: true,
  clean: false,
  plugins: [typertPlugin({ mode: 'workspace', faces: ['host'] })],
})
