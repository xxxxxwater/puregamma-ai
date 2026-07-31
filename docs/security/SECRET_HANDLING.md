# Secret Handling

Secrets include API keys, signing keys, webhook secrets, database credentials, provider tokens, and planned connector credentials.

## Never Commit

Never commit:

- `.env` with real values.
- Stripe keys.
- Plaid secrets or access tokens.
- Exchange API secrets.
- iMessage relay secret.
- SMTP password.
- OpenAI or data provider keys.

## Storage

Use:

- Local `.env` for development only.
- Secret manager for production.
- File-mounted secret for SFTP private keys.
- Encrypted database fields for user connector credentials when implemented.

## Logging Rules

Do not log:

- Bearer tokens.
- API keys.
- Webhook signatures.
- Plaid access tokens.
- Exchange secrets.
- iMessage HMAC secret.
- Raw provider payloads with sensitive user data.

## Rotation

Rotate immediately if:

- A secret was committed.
- A secret appeared in logs.
- A provider reports suspicious usage.
- An employee or contractor with access leaves.
- The customer contract requires scheduled rotation.

## Exchange and Wallet Rules

PureGamma must never store:

- Seed phrases.
- Wallet private keys.
- Exchange withdrawal keys.

Exchange keys must be read-only and encrypted before persistence.
