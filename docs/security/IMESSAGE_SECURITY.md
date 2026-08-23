# iMessage Security
iMessage delivery has two switchable providers selected by IMESSAGE_PROVIDER:
an opt-in self-hosted Mac relay (macos_relay) and the Photon-hosted provider
(photon). Neither is a general Apple server API, and neither provider is an
automatic fallback for the other.
The relay does not read the private Messages database.
## Trust Boundary
```text
PureGamma API -> HMAC-signed HTTPS/internal request -> Mac relay -> Messages.app
```
The relay should be treated as a sensitive component because it can send messages from the signed-in Apple ID.
## Controls
- HMAC signature with `IMESSAGE_RELAY_SECRET`.
- Timestamp replay tolerance.
- Idempotency key.
- Message length limit.
- API-level entitlement check.
- API-level per-user daily rate limit.
- Local relay SQLite delivery audit.
## Deployment Rules
- Do not expose relay publicly without network controls.
- Use HTTPS or private network tunneling outside localhost.
- Rotate relay secret if exposed.
- Restrict relay host access.
- Keep macOS updated.
- Confirm Messages.app login manually.
## Data Handling
- Store only delivery audit needed for idempotency.
- Do not inspect private Messages database.
- Avoid logging full message bodies.
- Treat phone numbers or Apple IDs as personal data.
## Photon Provider Controls
When IMESSAGE_PROVIDER=photon:
- Proxy bearer token is base64("{PHOTON_SERVER_URL}|{PHOTON_API_KEY}") and is
  never logged or persisted.
- Every send forwards the PureGamma idempotency key as the proxy
  Idempotency-Key header; local NotificationDelivery idempotency remains the
  trusted deduplication layer (some proxy versions ignore the header).
- Inbound webhook (/internal/imessage/photon/webhook) verifies the Photon
  X-Spectrum signature (v0:{timestamp}:{rawBody} HMAC-SHA256 with
  PHOTON_WEBHOOK_SECRET), a five-minute replay window, the event type and
  (when set) PHOTON_LINE_ID. PHOTON_LINE_ID is a line selector, not an auth
  credential.
- Production startup refuses missing PHOTON_API_KEY, PHOTON_SERVER_URL,
  PHOTON_HTTP_PROXY_URL or PHOTON_WEBHOOK_SECRET.
- Inbound media attachments are acknowledged but NOT processed (no attachment
  bytes exist in the webhook).
See docs/integrations/PHOTON_IMESSAGE.md.

## Limitations
- Delivery receipts are not guaranteed.
- Messages.app can require manual user action.
- AppleScript can fail after OS or app updates.
- Relay availability depends on Mac power, network, and logged-in user session.
