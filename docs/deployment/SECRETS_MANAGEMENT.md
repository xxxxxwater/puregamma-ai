# Secrets Management

Secrets must be injected through environment variables or a secret manager. Do not commit real credentials.

## Secret Classes

| Class | Examples | Handling |
| --- | --- | --- |
| Signing keys | `JWT_SECRET`, `IMESSAGE_RELAY_SECRET`, `STRIPE_WEBHOOK_SECRET` | High entropy, rotated carefully |
| Provider API keys | OpenAI, Stripe, Telegram, Plaid, X, Glassnode, Coinglass | Store in secret manager |
| User connector credentials | Plaid access tokens, exchange API secrets | Encrypt before persistence |
| Infrastructure credentials | Database URL, Redis URL, SMTP password | Use managed secret storage |

## Rotation

Recommended rotation process:

1. Create a new secret.
2. Deploy it to all services that need it.
3. Support old and new secret during transition when protocol allows it.
4. Rotate clients or credentials.
5. Remove the old secret.
6. Audit logs for unexpected failures.

## iMessage Relay Secret

`IMESSAGE_RELAY_SECRET` is shared between the API and relay. It signs `{timestamp}.{raw_body}` with HMAC-SHA256. Rotate both sides together.

## Stripe Webhook Secret

`STRIPE_WEBHOOK_SECRET` must match the Stripe webhook endpoint secret. Requests without a valid Stripe signature must be rejected in `BILLING_MODE=stripe`.

## Exchange Keys

Exchange key material must be:

- Read-only.
- Never withdrawal-enabled.
- Never trading-enabled unless a future separate trading product exists.
- Encrypted at rest before persistence.
- Deleted on disconnect.

## What Not To Store

PureGamma AI must never ask users for:

- Seed phrases.
- Wallet private keys.
- Exchange withdrawal permissions.
- Brokerage login credentials outside Plaid Link.

## Incident Response

If a secret may have leaked:

1. Revoke or rotate it immediately.
2. Disable affected integration.
3. Review logs for misuse.
4. Notify affected users or customers as required.
5. Document root cause and prevention.

See [Incident Runbook](../admin/INCIDENT_RUNBOOK.md).
