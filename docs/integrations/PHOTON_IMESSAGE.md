# Photon iMessage Provider

Photon (https://photon.codes) is a hosted iMessage delivery service. PureGamma
supports it as a **switchable provider** selected with `IMESSAGE_PROVIDER=photon`.

## 1. Relationship to the Mac Relay

- Photon is NOT a replacement for the self-hosted Mac relay
  (`apps/imessage-relay/`, `IMESSAGE_PROVIDER=macos_relay`) and it is never an
  automatic fallback for it. If the relay host fails, dispatches fail; they do
  not silently switch to Photon.
- Both providers share the same dispatcher gates: recipient verification,
  message length, daily rate limit, entitlement check, credit reservation,
  `NotificationDelivery` idempotency and retry policy.
- Verification codes (iMessage recipient binding) are sent through whichever
  provider `IMESSAGE_PROVIDER` selects.

## 2. Configuration

```env
IMESSAGE_PROVIDER=photon
PHOTON_API_KEY=
PHOTON_LINE_ID=
PHOTON_HTTP_PROXY_URL=https://imessage-swagger.photon.codes
PHOTON_SERVER_URL=
PHOTON_WEBHOOK_SECRET=
```

- `PHOTON_HTTP_PROXY_URL` is the base URL of the Photon **Advanced iMessage HTTP
  Proxy**, used for OUTBOUND sends.
- `PHOTON_SERVER_URL` is the Photon server used to construct the proxy bearer
  token (`base64("{PHOTON_SERVER_URL}|{PHOTON_API_KEY}")`). The two URLs have
  different responsibilities and must both be correct.
- `PHOTON_LINE_ID` selects/validates the allowed inbound line. It is **not** a
  sending credential; it only gates which line the webhook accepts.
- `PHOTON_WEBHOOK_SECRET` verifies Photon inbound webhooks.

Production startup fails fast when `IMESSAGE_PROVIDER=photon` and any of
`PHOTON_API_KEY`, `PHOTON_SERVER_URL`, `PHOTON_HTTP_PROXY_URL` or
`PHOTON_WEBHOOK_SECRET` is missing (same for `IMESSAGE_RELAY_SECRET` with
`macos_relay`).

## 3. Outbound Contract

Text:

```text
POST {PHOTON_HTTP_PROXY_URL}/send
Authorization: Bearer base64("{PHOTON_SERVER_URL}|{PHOTON_API_KEY}")
Idempotency-Key: <PureGamma idempotency key>
{"to": "<recipient>", "text": "<message>"}
```

Media (audio voice bubbles set `audio=true`):

```text
POST {PHOTON_HTTP_PROXY_URL}/send/file   (multipart/form-data)
to, file, audio=true
```

Result mapping (see `packages/notifications/imessage/photon_provider.py`):

- 2xx with `{"ok": true}` -> success.
- 4xx `VALIDATION_ERROR` / invalid-recipient codes -> permanent failure
  (`invalid_recipient`).
- 5xx, `UPSTREAM_ERROR`, timeouts, network errors -> `failed_retryable` with
  short exponential backoff.
- Missing configuration -> `missing_photon_configuration` (never an unhandled
  exception).

The provider never logs or persists the bearer token, message bodies, media
bytes or full recipients; `provider_response` is whitelisted to status fields
only.

## 4. Idempotency

Every PureGamma `idempotency_key` is forwarded as the proxy `Idempotency-Key`
header. Known limitation: some proxy versions do not honor that header. The
local `NotificationDelivery` idempotency layer remains the trusted
deduplication boundary either way, so retries can never double-send or
double-bill.

## 5. Inbound Webhook

Register Photon webhooks at:

```text
POST /internal/imessage/photon/webhook
```

Verification (Photon X-Spectrum signing):

- `X-Spectrum-Timestamp` / `X-Spectrum-Signature` headers;
- `HMAC-SHA256(PHOTON_WEBHOOK_SECRET, "v0:{timestamp}:{raw body}")`;
- five-minute replay window and constant-time comparison.

The route only processes `X-Spectrum-Event=messages` payloads with
`message.direction == "inbound"`, `message.platform == "iMessage"` and
`content.type == "text"`. It persists a `photon_inbound_tasks` row
(idempotent on the Photon message.id) and enqueues a Celery task, then
returns 2xx immediately — the webhook never waits on the LLM.

The worker (`puregamma.process_photon_inbound`) runs the SAME shared inbound
flow as the Mac relay (`/internal/imessage/inbound`): user matching,
verification status, `IMessageInboundEvent` dedupe, agent reply, billing and
limits. It then sends the reply through `PhotonIMessageProvider` with the
fixed idempotency key `photon-inbound-reply:{message_id}`, audited in
`notification_deliveries` WITHOUT the user-notification billing path.
Failures retry up to 3 attempts (1/5/30 min), then go
`failed_permanent`; a per-minute reaper recovers crashed or stuck rows.
Duplicate webhooks can never double-run the agent, double-bill, or
double-send a reply.

When `PHOTON_LINE_ID` is configured, the event line (space.phone / line ids)
must match it; mismatches are acknowledged with a diagnostic and ignored.

**Inbound media is not implemented.** Non-text attachments are acknowledged
with `{"status": "unprocessed"}`; the webhook carries no attachment bytes and
this must later be built on the Photon SDK/Proxy attachment download
capability. Do not pretend the webhook can read attachments.

## 6. Security

- Never commit `PHOTON_API_KEY`, `PHOTON_WEBHOOK_SECRET` or a working proxy
  token.
- `PHOTON_LINE_ID` is a line selector, not an auth credential.
- Keep the webhook endpoint reachable only by Photon; the signature check is
  the only trust boundary.
- Provider failures raise a provider-neutral ops alert
  ("iMessage provider is failing") carrying the provider name — never secrets
  or message content.

## 7. Testing

```bash
pytest tests/unit/test_photon_provider.py tests/unit/test_photon_inbound_worker.py tests/integration/test_imessage_photon_webhook.py tests/security/test_production_configuration.py tests/security/test_webhook_signatures.py tests/security/test_migration_chain.py tests/integration/test_imessage_relay.py tests/integration/test_agent_answer_api.py
```

See also [iMessage Relay](./IMESSAGE_RELAY.md) and
[iMessage Security](../security/IMESSAGE_SECURITY.md).
