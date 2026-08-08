# Email
PureGamma AI supports email notifications through SMTP.
## Configuration
```text
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=...
```
When `SMTP_HOST` is missing, the provider returns mock success.
## Recipient
The dispatcher reads `user_preferences.email_recipient`.
## Send Test
```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"email","message":"PureGamma email test. ","metadata":{"idempotency_key":"email-test-1"}}'
```
## Entitlements and Credits
- Cost: 1 credit.
- Free, Pro, Max, and Enterprise include email in current plan config.
## Production Notes
- Use a provider with bounce, complaint, and unsubscribe handling.
- Do not send portfolio-sensitive content unless email risk is accepted by the user or contract.
- Scrub SMTP credentials from logs.
