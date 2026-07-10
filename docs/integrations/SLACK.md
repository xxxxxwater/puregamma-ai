# Slack

PureGamma.ai supports Slack notifications through incoming webhooks.

All investment messages must include: `This is not financial advice.`

## Configuration

```text
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

The dispatcher first uses `user_preferences.slack_webhook_url`. The provider can also fall back to `SLACK_WEBHOOK_URL`.

## Mock Behavior

If the webhook is missing or starts with `mock`, the provider returns mock success.

## Send Test

```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"slack","message":"PureGamma Slack test. This is not financial advice.","metadata":{"idempotency_key":"slack-test-1"}}'
```

## Entitlements and Credits

- Cost: 1 credit.
- Max and Enterprise include Slack in current plan config.
- Pro does not include Slack in `packages/billing/plans.py`.

## Security

- Treat Slack webhooks as secrets.
- Do not log webhook URLs.
- Rotate if a webhook is exposed.
