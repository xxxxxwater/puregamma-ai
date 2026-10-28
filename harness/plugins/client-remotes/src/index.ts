import type { Context } from '@deepseek-ai/cordis'
import PureGammaClientGateway from '@puregamma/dsh-client-gateway'

export const name = 'puregamma-client-remotes'

/**
 * Mount the Host half of the one PureGamma Typert Remote assembly.
 *
 * The browser half (`./client`) mounts the generated `puregammaClient` Remote
 * namespace, but a Remote namespace only answers when a Host service with the
 * same key is running. Upstream mounts each Remote service from its owning
 * plugin's `apply` (for example `dsh-command-feedback`), so this plugin owns
 * `PureGammaClientGateway` the same way: unloading the plugin removes the Host
 * service and the browser contribution together. Every gateway method reads
 * its domain service lazily and returns an explicit `available: false` value
 * when that capability is not installed.
 */
export function apply(ctx: Context): void {
  ctx.plugin(PureGammaClientGateway)
}
