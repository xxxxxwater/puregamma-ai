# User Management

User records live in the `users` table and are exposed to admins through `GET /admin/users`.

## User Fields

| Field | Purpose |
| --- | --- |
| `email` | Login/user identifier |
| `name` | Display name |
| `role` | `user` or `admin` |
| `plan` | Current plan |
| `credit_balance` | Available credits |
| `stripe_customer_id` | Stripe mapping |

## Preferences

`user_preferences` stores:

- Preferred assets.
- Risk level.
- Preferred style.
- Notification channels.
- Email, Telegram, Slack, and iMessage recipients.

## Admin Operations

Current API is read-only for users. Direct database updates should be avoided except during controlled local development.

Before production, add:

- User role management endpoint with audit log.
- Account disable/enable endpoint.
- Data deletion workflow.
- User impersonation prohibition or audited support access flow.

## Security

- Admin role changes must require explicit approval.
- Avoid exposing recipient fields unnecessarily.
- User deletion must also handle connector secrets and generated data according to retention policy.
