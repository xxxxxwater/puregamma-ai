import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'

export const inject = ['slots']

function PureGammaHeroBrand() {
  return (
    <div
      aria-label="PureGamma"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 12,
        fontSize: 22,
        fontWeight: 650,
        letterSpacing: '-0.02em',
      }}
    >
      <svg
        aria-hidden="true"
        width="34"
        height="34"
        viewBox="0 0 34 34"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect x="1" y="1" width="32" height="32" rx="9" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M9 22.5V11.5h6.2c4.1 0 6.6 2 6.6 5.4 0 3.5-2.5 5.6-6.6 5.6H9Zm3.1-2.5h2.8c2.4 0 3.7-1 3.7-3.1 0-2-1.3-2.9-3.7-2.9h-2.8V20Z"
          fill="currentColor"
        />
        <path d="M23.6 11.5h2.1v11h-2.1z" fill="currentColor" opacity="0.45" />
      </svg>
      <span>PureGamma</span>
    </div>
  )
}

/** Mount PureGamma identity into the generic Harness conversation hero. */
export function apply(ctx: ClientContext): void {
  ctx.slots.inject('conversation.hero.brand.mark', () =>
    ctx.slots.register({ name: 'conversation.hero.brand.mark' }, PureGammaHeroBrand),
  )
}
