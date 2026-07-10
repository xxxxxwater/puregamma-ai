# Daily Brief

The Daily Brief is PureGamma.ai's core user workflow: one concise research update that combines market regime, top signals, risk context, portfolio impact, and delivery through the user's selected notification channel.

The brief is research only and must include: `This is not financial advice.`

## Content Model

A complete daily brief should include:

- Market regime.
- Key assets and top signals.
- Portfolio NAV and exposure changes when portfolio data is available.
- Risk summary and invalidation notes.
- Strategy or playbook highlights.
- Source freshness warnings.
- Compliance disclaimer.

Current implementation creates daily market reports through `POST /reports/daily`. Worker tasks can generate reports and send daily notification messages. Portfolio-aware content is planned until backend NAV sync exists.

## Delivery Channels

| Channel | Status | Notes |
| --- | --- | --- |
| Web app | Implemented | Reports page shows generated reports |
| Email | Implemented | Uses SMTP when configured, mock otherwise |
| Telegram | Implemented | Uses bot token when configured, mock otherwise |
| Slack | Implemented | Uses webhook when configured, mock otherwise |
| iMessage | Implemented via mock or Mac relay | Requires Max or Enterprise entitlement |

## iMessage Template

The iMessage template is in `packages/notifications/imessage/templates.py` and uses `IMESSAGE_DAILY_TEMPLATE` from `packages/reports/templates.py`.

## Scheduled Jobs

`packages/workers/scheduler.py` defines:

- `shared_daily_market_intelligence` at 00:00 UTC.
- `personalized_daily_reports` at 00:10 UTC.
- `send_daily_reports` at 00:20 UTC.
- Market anomaly scans every 15 minutes.
- Market regime refresh every 4 hours.

Run locally:

```bash
python -m packages.workers.scheduler
```

## User Controls

The product should expose:

- Enabled/disabled state.
- Preferred delivery channel.
- Local delivery time and timezone.
- Include portfolio flag.
- Include signal and risk flags.
- Message length constraints for iMessage.

The current frontend has mock daily-push preference data; a persistence API is still a TODO.

## Safety Rules

- Never represent daily brief content as a trade recommendation.
- Include source freshness and partial-data warnings.
- Do not send duplicate daily messages for the same user, channel, and schedule window.
- Enforce entitlements and credits before delivery.
