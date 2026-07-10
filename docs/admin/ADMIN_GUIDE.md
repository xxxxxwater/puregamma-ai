# Admin Guide

The admin surface is for operational review of users, reports, data sources, Stripe events, notification deliveries, and subscriptions.

Admins must not use PureGamma.ai outputs as investment advice. Admin views can expose user-sensitive data and must be access controlled.

## Access

Admin API endpoints require:

- Valid bearer token.
- User `role=admin`.

Protected endpoints:

```text
GET /admin/users
GET /admin/reports
GET /admin/data-sources
GET /admin/stripe-events
GET /admin/notifications
GET /admin/subscriptions
```

## Local Demo Admin

Seed data creates `demo@puregamma.ai` with admin role. Do not rely on this behavior in production.

## Admin Tasks

- Review user plan and role state.
- Inspect generated reports.
- Check data source status.
- Audit Stripe webhook events.
- Review notification delivery failures.
- Review subscription state.
- Triage incidents using [Incident Runbook](./INCIDENT_RUNBOOK.md).

## Safety Rules

- Do not expose admin pages publicly without authentication.
- Do not paste user secrets into support tools.
- Do not manually edit credits without audit trail.
- Do not claim a portfolio NAV is correct without source freshness checks.
- Do not suppress compliance disclaimers in user-facing content.
