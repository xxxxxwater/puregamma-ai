# STRC Event-Driven Credit Trade

## 1. Strategy objective

Evaluate issuer/event-driven credit dislocations where spread widening may exceed fundamental deterioration.

## 2. Target market

STRC credit/security exposure where reliable quotes and issuer data are legally available.

## 3. Asset universe

STRC and issuer-related collateral/risk proxies.

## 4. Time horizon

2-6 weeks.

## 5. Required data

Credit spread, issuer filings/news, corporate actions, liquidity, BTC collateral proxy if relevant, event calendar, legal/data-source review.

## 6. Signal inputs

Spread z-score, issuer event severity, liquidity, collateral shock proxy, news timestamp quality, credit-market regime.

## 7. Signal formula

`raw_score = spread_dislocation * 0.30 + collateral_stability * 0.20 + event_resolution_probability * 0.15 + liquidity_quality * 0.10 - issuer_stress * 0.15 - data_quality_risk * 0.10`

## 8. Entry condition

Internal research only: spread widens without matching deterioration in issuer quality and liquidity remains adequate.

## 9. Exit condition

Spread normalizes, issuer risk rises, event catalyst resolves, or liquidity degrades.

## 10. Invalidation condition

Issuer-specific stress, liquidity break, stale spread data, legal data issue, or BTC collateral shock.

## 11. Risk controls

Do not launch. Requires issuer-risk review, legal review, licensed data, and credit-specific drawdown controls.

## 12. Position sizing suggestion

No MVP sizing. Enterprise/internal research should use credit VaR, liquidity haircut, and event loss limit.

## 13. Backtest assumptions

Event studies require publication timestamps and point-in-time issuer data. Survivorship and stale quote bias are major risks.

## 14. Fee / slippage model

Use wide spread and low-liquidity assumptions; include financing/carry if applicable.

## 15. Liquidity constraints

No fill assumption without verified quote depth and settlement path.

## 16. Failure modes

Issuer default/stress, legal/regulatory event, stale quotes, liquidity disappearance, misleading collateral proxy.

## 17. Regime dependency

Highly dependent on credit regime and issuer-specific event cycle.

## 18. When not to use

Do not use in MVP or when spread/issuer data is unlicensed, stale, or incomplete.

## 19. Expected false positives

Apparent spread dislocations caused by stale marks, quote dispersion, or hidden issuer stress.

## 20. MVP readiness

Not ready: Do not launch.
