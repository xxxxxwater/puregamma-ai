# Tenant Isolation

Current MVP data model is user-scoped, not workspace or enterprise tenant scoped. Add tenant isolation before multi-customer enterprise deployment.

## Current State

Current models use `user_id` for reports, subscriptions, notifications, credit ledger, preferences, and backtests. Admin endpoints can view global data.

## Required Enterprise Model

Add:

- `tenants` table.
- `tenant_memberships` table.
- `tenant_id` on user-owned records.
- Tenant-scoped admin roles.
- Tenant-specific secrets and connector credentials.
- Tenant-specific data retention settings.

## Access Rules

- Users can access only their tenant data.
- Tenant admins can access only their tenant.
- Platform admins require audited break-glass access.
- Background jobs must filter by tenant.
- Data exports must be tenant-scoped.

## Operational Isolation

Enterprise/private deployments should consider:

- Dedicated database.
- Dedicated Redis.
- Dedicated secret manager namespace.
- Dedicated logging project.
- Separate iMessage relay if used.

## Current Warning

Do not market the current MVP as enterprise multi-tenant isolated until tenant-scoped models, tests, and audit logs exist.
