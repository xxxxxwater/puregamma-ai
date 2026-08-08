# iMessage Security
iMessage delivery is implemented through an opt-in self-hosted Mac relay. It is not a general Apple server API.
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
## Limitations
- Delivery receipts are not guaranteed.
- Messages.app can require manual user action.
- AppleScript can fail after OS or app updates.
- Relay availability depends on Mac power, network, and logged-in user session.
