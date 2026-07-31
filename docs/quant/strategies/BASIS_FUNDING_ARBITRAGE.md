# Basis Funding Arbitrage

## 1. Strategy objective

Evaluate market-neutral carry opportunities where funding or basis exceeds fees, slippage, borrow, margin, and counterparty risk.

## 2. Target market

Crypto spot, perpetuals, futures, and basis instruments across approved venues.

## 3. Asset universe

BTC, ETH, SOL initially; extend only after venue and borrow controls exist.

## 4. Time horizon

1 day to 4 weeks.

## 5. Required data

Funding, basis, order book depth, fees, borrow, margin requirements, venue health, settlement rules, wallet/exchange balances.

## 6. Signal inputs

Annualized carry, net carry after costs, basis convergence, depth, margin utilization, counterparty risk, liquidation buffer.

## 7. Signal formula

`raw_score = net_carry_hurdle * 0.30 + depth_quality * 0.20 + basis_stability * 0.15 + margin_buffer * 0.15 - counterparty_risk * 0.10 - liquidation_risk * 0.10`

## 8. Entry condition

Enterprise research only: net annualized carry exceeds hurdle after all costs and venue risk limits pass.

## 9. Exit condition

Carry compresses below hurdle, margin buffer falls, venue health deteriorates, or liquidity thins.

## 10. Invalidation condition

Exchange withdrawal issue, borrow failure, funding settlement change, liquidation risk, or counterparty risk breach.

## 11. Risk controls

Venue limits, counterparty limits, wallet/exchange balance reconciliation, liquidation buffer, no auto execution.

## 12. Position sizing suggestion

Size by liquidity, margin buffer, venue exposure, and portfolio counterparty cap. Never size by headline funding alone.

## 13. Backtest assumptions

Funding timestamps, settlement rules, fees, borrow, and margin must be point-in-time. Use conservative fills on both legs.

## 14. Fee / slippage model

Include maker/taker fees, spread, depth, borrow, funding settlement, transfer costs, and liquidation penalty assumptions.

## 15. Liquidity constraints

Max simulated participation determined by order book depth and stress-tested withdrawal/settlement capacity.

## 16. Failure modes

Exchange insolvency/withdrawal halt, funding regime flip, borrow recall, liquidation, stale order book, settlement mismatch.

## 17. Regime dependency

Often improves in crowded leverage regimes but counterparty and liquidation risk also rise.

## 18. When not to use

Do not use for general MVP. Do not use without real-time venue, margin, borrow, and balance data.

## 19. Expected false positives

Headline positive funding that disappears after fees, slippage, borrow, unavailable fills, or counterparty limits.

## 20. MVP readiness

Enterprise-only: not suitable for general MVP signal surface.
