# SOL/HYPE High Beta Rotation

## 1. Strategy objective

Track high-beta rotation between SOL and HYPE when broad crypto risk appetite improves, while capping confidence for liquidity and venue risk.

## 2. Target market

SOL and HYPE spot/perp markets.

## 3. Asset universe

SOL, HYPE.

## 4. Time horizon

2-10 days.

## 5. Required data

SOL/HYPE OHLCV, funding, OI, liquidations, order book depth, venue coverage, market breadth, BTC regime.

## 6. Signal inputs

Relative strength, funding reset, OI growth quality, liquidation distance, order book depth, BTC risk regime.

## 7. Signal formula

`raw_score = relative_strength * 0.30 + breadth * 0.20 + funding_reset * 0.15 + liquidity_depth * 0.15 - oi_crowding * 0.10 - liquidation_cluster_risk * 0.10`

## 8. Entry condition

Research signal activates after SOL or HYPE relative momentum turns positive for two sessions and funding is below stress threshold.

## 9. Exit condition

Relative strength rolls over, liquidity thins, liquidation clusters move near spot, or BTC regime turns risk-off.

## 10. Invalidation condition

HYPE loses trend support while SOL breadth weakens and OI rises.

## 11. Risk controls

Research-only cap, high liquidity haircut, no leverage, risk score visible before payoff language.

## 12. Position sizing suggestion

Small volatility-targeted allocation only in research simulations. Cap by the less liquid asset.

## 13. Backtest assumptions

Use point-in-time exchange availability. HYPE missing-history and venue survivorship must be disclosed.

## 14. Fee / slippage model

Higher fee/slippage assumptions than BTC/ETH. Slippage must increase sharply when participation exceeds depth.

## 15. Liquidity constraints

Max simulated participation 0.25-0.50% of 24h volume for HYPE unless order book data proves capacity.

## 16. Failure modes

Liquidity vacuum, exchange-specific pricing, crowded OI, social-driven false breakouts, data gaps.

## 17. Regime dependency

Only active in broad risk-on markets with improving alt breadth and contained BTC volatility.

## 18. When not to use

Do not use during risk-off, HYPE data outages, rising funding stress, or low weekend liquidity.

## 19. Expected false positives

KOL-led spikes, liquidation bounces, and venue-specific pumps without cross-venue confirmation.

## 20. MVP readiness

Research only: not eligible for high-confidence or actionable MVP signals.
