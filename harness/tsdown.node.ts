import type { UserConfig } from 'tsdown'

/**
 * Standard build for host-only PureGamma Harness packages.
 *
 * `fixedExtension: false` deliberately keeps the package.json contract at
 * `lib/index.js` + `lib/index.d.ts` for ESM `type: module` packages. Without it
 * tsdown emits `.mjs/.d.mts`, which diverges from the Harness package exports
 * and loader manifests.
 */
export function nodePlugin(entry = 'src/index.ts'): UserConfig {
  return {
    entry: [entry],
    format: 'esm',
    platform: 'node',
    target: 'es2024',
    outDir: 'lib',
    fixedExtension: false,
    dts: true,
    sourcemap: true,
    clean: true,
  }
}
