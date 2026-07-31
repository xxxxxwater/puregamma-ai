# HYPE Trend Following

## 1. Strategy objective

Observe HYPE trend continuation when price, liquidity, funding, and protocol activity align.

## 2. Target market

HYPE spot/perp markets where data is available and timestamped.

## 3. Asset universe

HYPE.

## 4. Time horizon

2-8 days.

## 5. Required data

OHLCV, funding, OI, liquidations, order book depth, protocol metrics, venue status.

## 6. Signal inputs

7-day trend support, higher highs, volatility contraction, funding stress, OI quality, protocol activity.

## 7. Signal formula

`raw_score = trend_slope * 0.25 + breakout_quality * 0.20 + volatility_contraction * 0.15 + protocol_activity * 0.15 - funding_stress * 0.10 - liquidity_risk * 0.15`

## 8. Entry condition

Research signal activates after a higher high follows volatility contraction with funding below stress threshold.

## 9. Exit condition

Exit research state when trend support fails, extension becomes vertical, or liquidation clusters move close to spot.

## 10. Invalidation condition

Loss of 7-day trend support with rising OI and negative market breadth.

## 11. Risk controls

No leverage, low confidence cap, strict liquidity filter, stale data penalty, research-only language.

## 12. Position sizing suggestion

Small research allocation only, volatility-targeted, capped by order book depth.

## 13. Backtest assumptions

Use point-in-time venue listing and avoid assuming data before HYPE was tradeable on the venue.

## 14. Fee / slippage model

Use high slippage assumptions; include spread, depth, and volatility participation penalty.

## 15. Liquidity constraints

Participation should be materially lower than BTC/ETH/SOL. No fill assumption without depth.

## 16. Failure modes

Venue concentration, thin books, social momentum reversal, liquidation cascade, protocol metric lag.

## 17. Regime dependency

Requires risk-on crypto regime and stable venue liquidity.

## 18. When not to use

Do not use when funding is stressed, liquidity is thin, protocol data is stale, or BTC regime is risk-off.

## 19. Expected false positives

KOL amplification, isolated exchange move, short squeeze without spot demand.

## 20. MVP readiness

Research only: not ready for actionable MVP signals.
