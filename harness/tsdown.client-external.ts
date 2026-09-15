import { isBuiltin } from 'node:module'
import type { UserConfig } from 'tsdown'

export interface ExternalClientBundleOptions {
  /** Runtime module-table entries supplied by the Harness web shell. */
  externals?: readonly string[]
}

function matches(names: ReadonlySet<string>, specifier: string): boolean {
  for (const name of names) {
    if (specifier === name || specifier.startsWith(`${name}/`)) return true
  }
  return false
}

/**
 * Build an out-of-tree PureGamma Harness client plugin using the same loader ABI
 * as DeepSeek Harness' in-repository clientBundle preset.
 *
 * The upstream preset intentionally discovers manifests only under its own
 * two-level `packages/<family>/<package>` tree. PureGamma plugins live in a
 * separate overlay workspace, so this preset preserves the runtime artifact
 * contract without modifying the pinned upstream submodule or pretending our
 * package lives inside it.
 *
 * Contract preserved here:
 * - Node half at `lib/index.js`.
 * - Browser half at `lib/client.js`.
 * - CJS body wrapped in `window.__ModuleLoader__.load({ id, factory })`.
 * - Shared platform identities stay external and resolve through factory
 *   `require`, preventing duplicate React/Cordis instances.
 */
export function externalClientBundle(
  id: string,
  options: ExternalClientBundleOptions = {},
): UserConfig[] {
  const requested = new Set([
    'react',
    'react/jsx-runtime',
    'react-dom',
    'react-dom/client',
    '@deepseek-ai/cordis',
    '@deepseek-ai/dsh-client-store',
    '@deepseek-ai/dsh-client-ui-slots',
    '@deepseek-ai/dsh-client-ui-primitives',
    '@deepseek-ai/dsh-client-ui-dockkit',
    ...(options.externals ?? []),
  ])
  const isRequested = (specifier: string): boolean => matches(requested, specifier)

  const host: UserConfig = {
    name: id,
    entry: ['lib/types/index.js'],
    outDir: 'lib',
    format: ['esm'],
    platform: 'node',
    target: 'es2024',
    fixedExtension: false,
    dts: false,
    clean: false,
    deps: {
      neverBundle: (specifier: string) => isBuiltin(specifier),
      alwaysBundle: (specifier: string) => !isBuiltin(specifier),
    },
  }

  const client: UserConfig = {
    name: `${id}/client`,
    entry: { client: 'lib/types/client/index.js' },
    outDir: 'lib',
    format: 'cjs',
    platform: 'browser',
    target: 'es2024',
    fixedExtension: false,
    dts: false,
    sourcemap: true,
    clean: false,
    deps: {
      neverBundle: isRequested,
      alwaysBundle: (specifier: string) => !isRequested(specifier),
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV ?? 'production'),
      'import.meta.env.MODE': JSON.stringify(process.env.NODE_ENV ?? 'production'),
      'import.meta.env': JSON.stringify({ MODE: process.env.NODE_ENV ?? 'production' }),
    },
    outputOptions: {
      entryFileNames: 'client.js',
      sourcemapExcludeSources: false,
      banner: `window.__ModuleLoader__.load({ id: ${JSON.stringify(id)}, factory: (require) => {`,
      footer: 'return module.exports; } });',
      intro: 'var module = { exports: {} }; var exports = module.exports;',
    },
  }

  return [host, client]
}
