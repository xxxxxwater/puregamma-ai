# Notification Deliveries
Notification deliveries are stored in `notification_deliveries` and exposed through:
```text
GET /notifications/deliveries
GET /admin/notifications
```
## Delivery Fields
| Field | Purpose |
| --- | --- |
| `channel` | email, telegram, slack, imessage |
| `recipient` | Destination identifier |
| `payload` | Message payload |
| `status` | sent, failed, skipped, pending |
| `provider_response` | Safe provider detail |
| `idempotency_key` | Duplicate prevention |
| `retry_count` | Retry count |
| `sent_at` | Send timestamp |
## Skipped Reasons
Common skipped reasons:
- `missing_recipient`
- `entitlement_denied`
- `message_too_long`
- `daily_rate_limit`
- `insufficient_credits`
## Failure Handling
Provider failures set status `failed` and refund credits. Admins should inspect provider response, check credentials, and retry with the same idempotency key only if they expect the same recorded delivery to be returned.
## Duplicate Prevention
Do not generate random idempotency keys for scheduled daily messages. Use deterministic keys such as:
```text
daily-{user_id}-{channel}-{date}
```
## Privacy
Notification payloads can contain portfolio-sensitive research. Restrict admin access and avoid copying message bodies into external support systems.
