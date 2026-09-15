import type { Context as ClientContext } from '@deepseek-ai/cordis'
import pureGammaClientRemote from '@puregamma/dsh-client-gateway/remote'
import type {} from '@deepseek-ai/dsh-api-gateway/client'
import type {} from '@puregamma/dsh-client-gateway/remote'

export const inject = ['remote']

/** Mount PureGamma's generated Host Remote contribution for exactly this client fiber. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return ctx.remote.$mount(pureGammaClientRemote)
}
