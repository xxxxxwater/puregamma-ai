# Adding a Notification Provider

Notification providers live in `packages/notifications`.

All investment notifications must preserve: `Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.`

## Existing Interface

```python
@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    provider: str
    response: dict

class NotificationProvider(Protocol):
    channel: str

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        raise NotImplementedError
```

## Steps

1. Implement provider class in `packages/notifications`.
2. Add channel-to-action mapping in `NotificationDispatcher` if it consumes credits.
3. Add credit cost in `packages/billing/credits.py`.
4. Add plan channel entitlement in `packages/billing/plans.py`.
5. Add provider selection in `NotificationDispatcher._provider`.
6. Add recipient preference field if needed.
7. Add environment variables and docs.
8. Add tests for success, missing recipient, entitlement denied, insufficient credits, provider failure refund, and idempotency.

## Idempotency

Providers must accept `idempotency_key`. If the external provider supports idempotency, pass it through. If not, PureGamma still records delivery idempotency in `notification_deliveries`.

## Failure Behavior

Provider failure should return:

```python
NotificationResult(False, "provider_name", {"error": "safe_error_code"})
```

The dispatcher refunds credits when `ok=False`.

## Security

- Do not log credentials.
- Do not log full sensitive messages for enterprise users.
- Validate recipient format where possible.
- Keep provider response safe for admin display.
