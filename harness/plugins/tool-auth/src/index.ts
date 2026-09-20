import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@puregamma/dsh-auth'

export const name = 'puregamma-tool-auth'
export const inject = ['tools', 'pgAuth']

function authStatusTool(ctx: Context) {
  return defineTool({
    name: 'auth_status',
    description: 'Read privacy-minimized PureGamma account status. It intentionally omits email address, user id, external customer ids and credentials.',
    parameters: {},
    output: {
      schema: {
        type: 'object', additionalProperties: false, properties: {
          signedIn: { type: 'boolean', required: true },
          role: { type: 'string', required: true },
          plan: { type: 'string', required: true },
          membershipTier: { type: 'string' },
          locale: { type: 'string', required: true },
          authProvider: { type: 'string', required: true },
          loginMethods: { type: 'array', required: true, items: { type: 'string' } },
          emailVerified: { type: 'boolean', required: true },
        },
      },
      render: (_args, value) => [{ type: 'text', text: `PureGamma account: ${value.plan} plan, role ${value.role}, locale ${value.locale}, provider ${value.authProvider}.` }],
    },
    isConcurrencySafe: () => true,
    async execute() {
      const user = await ctx.pgAuth.currentUser()
      return {
        signedIn: true,
        role: user.role,
        plan: user.plan,
        ...(user.membershipTier === undefined ? {} : { membershipTier: user.membershipTier }),
        locale: user.locale,
        authProvider: user.authProvider,
        loginMethods: [...user.loginMethods],
        emailVerified: user.emailVerified,
      }
    },
    presentCall: () => ({ card: 'generic', title: 'Check account status', kind: 'other' }),
  })
}

export function apply(ctx: Context): void {
  ctx.tools.register(authStatusTool(ctx))
}
