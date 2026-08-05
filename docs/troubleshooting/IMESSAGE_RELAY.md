# iMessage Relay Troubleshooting

## Relay Health

```bash
curl http://localhost:8787/health
```

Expected:

```json
{"status":"ok","service":"puregamma-imessage-relay","secret_configured":true}
```

## `invalid_hmac_signature`

Fix:

- Confirm API and relay share the same `IMESSAGE_RELAY_SECRET`.
- Check system clocks.
- Confirm body is signed exactly as sent.
- Confirm timestamp is within `IMESSAGE_REPLAY_TOLERANCE_SECONDS`.

## `unsupported_os`

Cause: Relay is not running on macOS.

Fix: Run real relay on a Mac with Messages.app. Use non-macOS only for HMAC/idempotency tests.

## `message_too_long`

Fix:

- Reduce message length.
- Check `IMESSAGE_MAX_MESSAGE_LENGTH`.

## Duplicate Delivery

If relay returns `duplicate=true`, the idempotency key was already used. This is expected duplicate prevention.

## Messages.app Failure

Fix:

- Open Messages.app.
- Confirm Apple ID is signed in.
- Send manual message to recipient.
- Restart Messages.app or the relay.

## API Delivery Skipped

Reasons:

- Missing recipient.
- Entitlement denied.
- Daily rate limit.
- Insufficient credits.

Check:

```text
GET /notifications/deliveries
GET /billing/subscription
```
