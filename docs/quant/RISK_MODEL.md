# Risk Model

`risk_score` is a 0-100 composite. Higher means more adverse conditions, larger model uncertainty, or higher probability that an apparently good setup becomes untradeable.

## Buckets

- `risk_low`: 0-30
- `risk_medium`: 31-60
- `risk_high`: 61-80
- `risk_extreme`: 81-100

## Factors

| Factor | Intent |
| --- | --- |
| Realized volatility | Penalize unstable price paths. |
| Implied/proxy volatility | Use options or proxy vol where available. |
| Liquidity | Penalize weak turnover, shallow books, and low capacity. |
| Funding rate | Penalize crowded leverage and carry cost. |
| Open interest | Penalize high OI versus volume. |
| Liquidation clusters | Penalize liquidation risk near spot. |
| Concentration | Penalize portfolio crowding in one asset or theme. |
| Correlation | Penalize hidden beta across positions. |
| Drawdown | Penalize strategies already in drawdown. |
| Macro regime | Penalize risk-off or unstable cross-asset regimes. |
| Event risk | Penalize issuer, governance, legal, and scheduled catalyst risk. |
| Counterparty/exchange risk | Penalize venue, custody, settlement, and borrow risks. |
| Data quality risk | Penalize stale, missing, or unlicensed data. |

## Implementation

`packages/risk/scoring.py` now exposes:

- `risk_score_for_quote`
- `risk_score_breakdown_for_quote`
- `risk_bucket`
- `data_quality_risk`

The implementation remains conservative and can be expanded as real data adapters mature.
