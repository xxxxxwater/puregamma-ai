import type { Context as ClientContext } from '@deepseek-ai/cordis'
import pureGammaClientRemote from '@puregamma/dsh-client-gateway/remote'
import type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
import type {} from '@puregamma/dsh-client-gateway/remote'

export type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'
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
