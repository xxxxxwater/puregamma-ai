# Telegram

PureGamma.ai supports Telegram notifications through a Telegram Bot token.

All investment messages must include: `This is not financial advice.`

## Configuration

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
```

When `TELEGRAM_BOT_TOKEN` is missing, or the recipient starts with `mock`, the provider returns mock success.

## Recipient

The current dispatcher reads `user_preferences.telegram_chat_id`.

Seeded demo value:

```text
mock-telegram-chat
```

## Send Test

```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"telegram","message":"PureGamma Telegram test. This is not financial advice.","metadata":{"idempotency_key":"telegram-test-1"}}'
```

## Entitlements and Credits

- Cost: 1 credit.
- Plan channels: Pro, Max, and Enterprise include Telegram.
- Free users are skipped with `entitlement_denied`.

## Troubleshooting

- Missing recipient: set `telegram_chat_id`.
- Skipped delivery: check plan entitlement and credits.
- Provider failure: verify bot token and chat ID.
- Duplicate result: reuse of same idempotency key is expected to return existing delivery.
