# Data Privacy
PureGamma AI can process sensitive financial research context even without custody or trading.
## Data Classes
| Data | Sensitivity | Notes |
| --- | --- | --- |
| Email and name | Personal | Required for user account |
| Notification recipients | Personal/restricted | Phone, chat IDs, webhooks |
| Stripe customer/subscription IDs | Restricted | Billing metadata |
| Reports and signals | Restricted | May reveal portfolio interests |
| Plaid holdings and transactions | Restricted | Planned |
| Exchange balances and trades | Restricted | Planned |
| Wallet addresses | Restricted | Public on-chain but tied to user identity |
| Admin audit logs | Restricted | Planned |
## Minimization
- Store normalized provider data instead of full raw payloads where possible.
- Do not retain provider secrets after disconnect.
- Do not log message bodies or portfolio positions unless necessary and access controlled.
- Do not expose full recipient values in shared dashboards.
## Deletion Requests
Deletion flow should:
1. Verify requester identity.
2. Disconnect Plaid/exchange/wallet credentials.
3. Delete or anonymize reports, preferences, notifications, and portfolio data.
4. Retain only legally required billing/audit records.
5. Confirm completion to user.
See [Incident Runbook](../admin/INCIDENT_RUNBOOK.md#11-user-data-deletion-request).
## Enterprise Data
Enterprise/private deployments may require:
- Separate database.
- Separate secrets.
- Separate observability project.
- Contract-specific retention.
- Export and deletion attestations.
