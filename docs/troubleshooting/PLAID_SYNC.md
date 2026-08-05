# Plaid Sync Troubleshooting

Plaid backend sync is planned. Use this guide for implementation and future operations.

Plaid data is investments data only and is not used for trading.

## Link Token Fails

Check:

- `PLAID_ENV`.
- `PLAID_CLIENT_ID`.
- `PLAID_SECRET`.
- Redirect URI matches Plaid dashboard.
- Product includes `investments`.

## Public Token Exchange Fails

Common causes:

- Public token expired.
- Public token already exchanged.
- Wrong Plaid environment.
- Missing secret.

Mitigation:

- Ask user to restart Plaid Link.
- Do not log token values.

## Holdings Missing

Check:

- Account supports investments.
- User selected correct institution/account.
- Plaid item needs re-authentication.
- Sync job completed.

## Stale Holdings

Mitigation:

- Mark source stale.
- Show Portfolio NAV as partial.
- Retry sync with backoff.

## Disconnect

Disconnect must delete encrypted access token and stop future sync. Historical data retention depends on user request and policy.
