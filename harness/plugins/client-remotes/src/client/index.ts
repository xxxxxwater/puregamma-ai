import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { ClientRemote as HarnessClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
import type { TypertClientRemote } from '@deepseek-ai/dsh-typert-protocol'
import pureGammaClientRemote from '@puregamma/dsh-client-gateway/remote'
import type {} from '@puregamma/dsh-client-gateway/remote'

/** PureGamma Client Remote assembly: native Harness carrier plus generated PureGamma namespaces. */
export type ClientRemote = HarnessClientRemote & TypertClientRemote
export type {} from '@puregamma/dsh-client-gateway/remote'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Generated Remote namespaces selected by the PureGamma Client assembly. */
    remote: ClientRemote
  }
}

/** Required Client service: the native Harness Remote carrier. */
export const inject = ['remote']

/** Mount PureGamma's generated Host Remote contribution for exactly this client fiber. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return ctx.remote.$mount(pureGammaClientRemote)
}
