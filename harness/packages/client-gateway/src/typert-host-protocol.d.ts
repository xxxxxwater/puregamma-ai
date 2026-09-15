declare module '@deepseek-ai/dsh-typert-protocol' {
  import type { Context, Service } from '@deepseek-ai/cordis'

  export interface TypertGatewayBindingOptions {
    readonly namespace?: string
  }

  export interface TypertGatewayBinding<ServiceType = unknown> {
    readonly service: ServiceType
    readonly serviceKey: string
    readonly namespace: string
  }

  export abstract class TypertRemoteService<T = never> extends Service<T> {
    readonly typertRemote: TypertGatewayBinding<this>
    protected constructor(
      ctx: Context,
      serviceKey: string,
      options?: TypertGatewayBindingOptions,
    )
  }

  export function Remote(exportName: string): <This extends object, Value extends (...args: any[]) => any>(
    value: Value,
    context: ClassMethodDecoratorContext<This, Value>,
  ) => void
}
