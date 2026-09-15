import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
import type { TypertRemoteNamespace } from '@deepseek-ai/dsh-typert-protocol'
import pureGammaClientRemote from '@puregamma/dsh-client-gateway/remote'
import type {} from '@puregamma/dsh-client-gateway/remote'

/** Extend the native Harness ClientRemote with the generated PureGamma namespace. */
declare module '@deepseek-ai/dsh-api-gateway/client' {
  interface ClientRemote {
    /** Generated PureGamma Host capability namespace. */
    readonly puregammaClient: TypertRemoteNamespace<'puregammaClient'>
  }
}

export type { ClientRemote }
export type {} from '@puregamma/dsh-client-gateway/remote'

/** Required Client service: the native Harness Remote carrier. */
export const inject = ['remote']

/** Mount PureGamma's generated Host Remote contribution for exactly this client fiber. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return ctx.remote.$mount(pureGammaClientRemote)
}
