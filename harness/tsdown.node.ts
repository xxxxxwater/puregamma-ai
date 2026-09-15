import type { UserConfig } from 'tsdown'

/** Standard build for host-only PureGamma Harness packages. */
export function nodePlugin(entry = 'src/index.ts'): UserConfig {
  return {
    entry: [entry],
    format: 'esm',
    outDir: 'lib',
    dts: true,
    sourcemap: true,
    clean: true,
  }
}
