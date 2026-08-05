# Portfolio NAV Disclosure

Portfolio NAV is an estimate for research context.

## Required Disclosure

```text
Portfolio NAV is an estimate based on available data. It is not tax advice, not financial advice, and not an official broker, custodian, or exchange statement.
```

## Required Warnings

Show warnings when:

- Data is partial.
- Source is stale.
- Price is stale or missing.
- Cost basis is unavailable.
- Stablecoin peg may be impaired.
- A connector is disconnected.
- Manual positions are included.

## Current Implementation

Backend NAV sync and persistence are live: snapshots are captured per source, refreshed by a scheduled job, and marked `partial`/`stale` when a source is missing or delayed. See [Portfolio NAV](../product/PORTFOLIO_NAV.md) for the supported sources and freshness behavior.

## User Support Rule

If a user reports incorrect NAV, do not state that the product value is official. Ask for source, timestamp, account, and position details, then follow [Portfolio NAV Troubleshooting](../troubleshooting/PORTFOLIO_NAV.md).
