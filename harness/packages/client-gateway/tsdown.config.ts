import { defineConfig } from 'tsdown'
import { typertPlugin } from '@deepseek-ai/dsh-typert-generator/tsdown'

export default defineConfig({
  entry: ['src/index.ts'],
  format: 'esm',
  platform: 'node',
  target: 'es2024',
  outDir: 'lib',
  fixedExtension: false,
  dts: false,
  sourcemap: true,
  clean: false,
  plugins: [typertPlugin({ mode: 'package', faces: ['host'] })],
})
