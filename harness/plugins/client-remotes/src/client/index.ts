import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
import type { TypertRemoteNamespace } from '@deepseek-ai/dsh-typert-protocol'
import pureGammaClientRemote from '@puregamma/dsh-client-gateway/remote'
import type {
  PureGammaClientRemote,
  PureGammaAccountView,
  PureGammaBillingView,
  PureGammaNotificationsView,
  PureGammaQuantRuntimeView,
} from '@puregamma/dsh-client-gateway'
import type {} from '@puregamma/dsh-client-gateway/remote'

/**
 * Extend the native Harness ClientRemote with the generated PureGamma
 * namespace. The structural contract is anchored to the Host gateway types;
 * the Typert namespace remains an intersection so generated protocol members
 * cannot be silently replaced by a hand-written browser transport.
 */
declare module '@deepseek-ai/dsh-api-gateway/client' {
  interface ClientRemote {
    /** Generated PureGamma Host capability namespace. */
    readonly puregammaClient: TypertRemoteNamespace<'puregammaClient'> & PureGammaClientRemote
  }
}

export type { ClientRemote, PureGammaClientRemote, PureGammaAccountView, PureGammaBillingView, PureGammaNotificationsView, PureGammaQuantRuntimeView }
export type {} from '@puregamma/dsh-client-gateway/remote'

/** Required Client service: the native Harness Remote carrier. */
export const inject = ['remote']

/** Mount PureGamma's generated Host Remote contribution for exactly this client fiber. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return ctx.remote.$mount(pureGammaClientRemote)
}
