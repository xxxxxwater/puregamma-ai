import { defineConfig } from 'tsdown'

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
  external: [
    '@deepseek-ai/cordis',
    '@deepseek-ai/dsh-typert-protocol-runtime',
  ],
})
