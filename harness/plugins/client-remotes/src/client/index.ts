import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
import pureGammaClientRemote from '@puregamma/dsh-client-gateway/remote'
import type {} from '@puregamma/dsh-client-gateway/remote'

/**
 * PureGamma Client Remote assembly follows the native Harness contract:
 * generated `/remote` declarations extend `TypertRemoteNamespaceMap`, while
 * this package owns the explicit runtime mount for the current Client fiber.
 * No hand-written business method list or browser transport is introduced.
 */
export type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
export type {} from '@puregamma/dsh-client-gateway/remote'

/** Required Client service: the native Harness Remote carrier. */
export const inject = ['remote']

/** Mount PureGamma's generated Host Remote contribution for exactly this client fiber. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return ctx.remote.$mount(pureGammaClientRemote)
}
