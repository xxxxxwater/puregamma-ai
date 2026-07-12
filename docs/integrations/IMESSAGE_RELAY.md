# iMessage Relay

iMessage has no ordinary server API for third-party server-side sending. PureGamma AI supports iMessage delivery through a self-hosted Mac relay controlled by the user or deployment operator.

The relay does not read the private Messages database. It only receives signed send requests from PureGamma API and asks Messages.app to send a message through AppleScript.

## 1. No General iMessage Server API

Apple does not provide a general server API equivalent to SMTP, Slack webhook, or Telegram Bot API for iMessage delivery. PureGamma therefore treats iMessage as an opt-in local relay integration.

## 2. Self-hosted Mac Relay

The relay is a FastAPI service in:

```text
apps/imessage-relay/
```

It exposes:

```text
GET /health
POST /send
```

## 3. Mac Mini Requirement

For real sends, run the relay on a macOS host such as a Mac mini. Non-macOS hosts can validate HMAC and idempotency but return `unsupported_os` for actual sends.

## 4. Apple ID and Messages.app Requirement

The Mac must:

- Be signed in to Apple ID.
- Have Messages.app enabled.
- Be able to send iMessage to the target recipient manually.
- Keep the user session available for AppleScript execution.

## 5. How API Server Calls Relay

API notification flow:

1. User or scheduler requests iMessage delivery.
2. `NotificationDispatcher` checks recipient, entitlement, message length, daily limit, credits, and idempotency.
3. `MacOSIMessageRelayClient` builds JSON payload.
4. API signs the request with `IMESSAGE_RELAY_SECRET`.
5. Relay verifies HMAC, timestamp, and idempotency key.
6. Relay calls `osascript scripts/send_imessage.applescript`.
7. API records `NotificationDelivery`.

## 6. HMAC Signing

Headers:

```text
X-PG-Timestamp: <unix-seconds>
X-PG-Signature: <hmac-sha256-hex>
X-PG-Idempotency-Key: <key>
```

Signature:

```text
HMAC_SHA256(IMESSAGE_RELAY_SECRET, "{timestamp}.{raw_body}")
```

Relay rejects missing, invalid, or replayed signatures.

## 7. Idempotency

The API and relay both use idempotency:

- API stores `notification_deliveries.idempotency_key`.
- Relay stores delivery rows in local SQLite by `idempotency_key`.
- Duplicate relay sends return the existing delivery record.

## 8. Rate Limiting

The API enforces:

```text
IMESSAGE_RATE_LIMIT_PER_USER_PER_DAY=20
IMESSAGE_MAX_MESSAGE_LENGTH=3000
```

Daily count is based on sent iMessage deliveries for the user.

## 9. Message Templates

Template function:

```text
packages/notifications/imessage/templates.py
```

Every investment-related message must include:

```text
Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

## 10. Security Limitations

- The relay depends on a logged-in macOS user session.
- AppleScript automation can fail if Messages.app changes state.
- Relay should not be publicly exposed.
- Relay must not log message bodies unnecessarily.
- Relay cannot guarantee delivery receipts.
- Relay does not read the private Messages database.

## 11. Launch Agent Setup

Use the bundled install script as a starting point:

```bash
cd apps/imessage-relay
chmod +x scripts/install_launch_agent.sh
./scripts/install_launch_agent.sh
```

Review the generated LaunchAgent before production use. Ensure `IMESSAGE_RELAY_SECRET`, DB path, and Python environment are set correctly.

## 12. Testing Mock Mode

API mock:

```text
IMESSAGE_PROVIDER=mock
```

Send:

```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"imessage","message":"Test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.","metadata":{"idempotency_key":"imessage-test-1"}}'
```

Relay health:

```bash
curl http://localhost:8787/health
```

## 13. Troubleshooting

### Relay Offline

Symptoms:

- API delivery status `failed`.
- Provider response contains connection error.
- `/health` unreachable.

Checks:

```bash
curl http://localhost:8787/health
launchctl list | grep puregamma
```

Mitigation:

- Restart relay.
- Verify `IMESSAGE_RELAY_SECRET`.
- Check firewall and reverse proxy.

### Messages.app Not Logged In

Symptoms:

- Relay request succeeds but AppleScript send fails.
- Manual send from Messages.app fails.

Mitigation:

- Sign in to Apple ID.
- Send a manual test message.
- Restart Messages.app.

### Failed Send

Symptoms:

- Relay response `status=failed`.
- `stderr` contains AppleScript or Messages.app error.

Mitigation:

- Verify recipient format.
- Reduce message length.
- Confirm Messages.app can send manually.

### Duplicate Send Prevention

Symptoms:

- API returns existing delivery for same idempotency key.
- Relay response contains `duplicate=true`.

Expected behavior:

- Do not retry with a new key unless you intentionally want another message.
- Keep deterministic keys for scheduled daily sends.

See [iMessage Relay Troubleshooting](../troubleshooting/IMESSAGE_RELAY.md).
