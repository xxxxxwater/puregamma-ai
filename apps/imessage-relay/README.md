# PureGamma.ai iMessage Relay

The relay is a self-hosted FastAPI service for users who choose to run iMessage delivery from their own Mac. It does not read the Messages private database and does not bypass Apple security controls.

## Run

```bash
cd apps/imessage-relay
export IMESSAGE_RELAY_SECRET=change-me
uvicorn relay:app --host 127.0.0.1 --port 8787
```

`POST /send` requires:

- `X-PG-Timestamp`
- `X-PG-Signature` as HMAC-SHA256 over `{timestamp}.{raw_body}`
- `X-PG-Idempotency-Key`

Non-macOS hosts return `unsupported_os` after validating HMAC and idempotency. macOS hosts call `scripts/send_imessage.applescript` through `osascript`.
