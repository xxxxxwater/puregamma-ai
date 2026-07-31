# Portfolio NAV Troubleshooting

Portfolio NAV is an estimate and not tax advice, financial advice, or an official statement.

## Incorrect NAV Reported

Collect:

- User ID.
- Timestamp.
- Account/source.
- Asset and quantity.
- Expected value and source statement.
- Whether data is Plaid, exchange, on-chain, or manual.

## Common Causes

- Source failed to sync.
- Price is stale.
- Unsupported asset mapping.
- Stablecoin depeg or wrong peg assumption.
- Duplicate position across sources.
- Missing cost basis.
- Chain RPC lag.
- Exchange sub-account not included.
- Plaid holdings delayed.

## Immediate Mitigation

- Mark NAV `partial_data=true`.
- Mark stale source in UI.
- Exclude clearly invalid source from aggregation if needed.
- Re-run sync after credentials or provider recover.

## Price Debugging

Check:

- Price source.
- Price timestamp.
- Asset symbol mapping.
- Stablecoin handling.
- Last known price fallback.

## Stablecoin Issues

Do not assume $1 if:

- Market price is materially off peg.
- Token contract is unsupported.
- Liquidity is low.
- Chain data is stale.

## User Communication

Use:

```text
Portfolio NAV is an estimate based on available data and may be partial while we review the affected source.
```

Do not say NAV is official or guaranteed accurate.
