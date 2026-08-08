# Database Schema
Models are defined in `packages/database/models.py`.
## Implemented Tables
| Table | Purpose | Key fields |
| --- | --- | --- |
| `users` | User account and plan state | `id`, `email`, `name`, `role`, `plan`, `credit_balance`, `stripe_customer_id` |
| `user_preferences` | User research and delivery preferences | `preferred_assets`, `risk_level`, `notification_channels`, recipients |
| `subscriptions` | Stripe subscription state | `stripe_subscription_id`, `plan_name`, `status`, `current_period_end` |
| `subscription_plans` | Seeded plan config | `monthly_credits`, `max_daily_reports`, `allowed_data_sources`, `stripe_price_id` |
| `credit_ledger` | Credit grants and consumption | `action`, `credits_delta`, `balance_after`, `metadata` |
| `stripe_webhook_events` | Webhook idempotency/audit | `stripe_event_id`, `event_type`, `processed`, `raw_payload_hash` |
| `assets` | Supported asset registry | `symbol`, `name`, `category`, `is_active` |
| `market_snapshots` | Point-in-time market data | `asset_id`, `price`, `volume_24h`, `funding_rate`, `open_interest` |
| `shared_market_intelligence` | Reusable market summary | `market_regime`, `summary_markdown`, `assets`, `source_snapshot_ids` |
| `signals` | Research signals | `asset`, `direction`, `confidence`, `risk_score`, `thesis` |
| `reports` | Generated reports | `user_id`, `title`, `report_type`, `content_markdown`, `assets` |
| `alerts` | Alert records | `asset`, `message`, `channel`, `status`, `idempotency_key` |
| `notification_deliveries` | Notification delivery audit | `channel`, `recipient`, `payload`, `status`, `provider_response`, `idempotency_key` |
| `backtest_runs` | Mock backtest results | `strategy_name`, `asset`, `params_json`, `result_json`, `credits_spent` |
## Important Constraints
- `users.email` is unique.
- `subscriptions.stripe_subscription_id` is unique.
- `stripe_webhook_events.stripe_event_id` is unique.
- `notification_deliveries.idempotency_key` is unique.
- `alerts.idempotency_key` is unique.
## Seed Data
`packages/database/seed.py` seeds:
- Plans from `packages/billing/plans.py`.
- Assets: BTC, ETH, SOL, HYPE, MSTR, STRC.
- Demo admin user: `demo@puregamma.ai`.
## Planned Portfolio Schema
Portfolio NAV needs new tables before production:
- `portfolio_accounts`: source, provider account ID, user ID, status.
- `portfolio_positions`: account, asset, quantity, price, value, timestamp.
- `portfolio_transactions`: normalized activity from Plaid/exchange/on-chain sources.
- `portfolio_nav_snapshots`: NAV, allocation, partial-data flag, source freshness.
- `connector_credentials`: encrypted Plaid/exchange token material.
- `wallet_addresses`: public wallet addresses by user and chain.
## Schema Migrations
Alembic owns production schema evolution. Add a reviewed revision under
`packages/database/alembic/versions` for every ORM schema change and run
`python -m scripts.db_migrate check` before release.
