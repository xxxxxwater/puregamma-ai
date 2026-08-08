# ETH/BTC Rotation
## 1. Strategy objective
Identify periods when ETH is likely to outperform BTC after BTC volatility cools and ETH/BTC relative strength improves.
## 2. Target market
ETH/BTC relative value and ETH-USD/BTC-USD proxy baskets.
## 3. Asset universe
ETH, BTC, ETH/BTC pair where available.
## 4. Time horizon
1-4 weeks.
## 5. Required data
ETH/BTC OHLCV, ETH and BTC funding/OI, BTC realized volatility, BTC dominance, alt breadth, on-chain/protocol activity if available.
## 6. Signal inputs
ETH/BTC close versus 20-day moving average, BTC volatility compression, relative volume, funding spread, market breadth.
## 7. Signal formula
`raw_score = rs_reclaim * 0.30 + btc_vol_compression * 0.20 + breadth * 0.20 + relative_volume * 0.10 - funding_spread_crowding * 0.10 - btc_dominance_breakout * 0.10`
## 8. Entry condition
ETH/BTC closes above the 20-day moving average after BTC realized volatility declines and breadth improves.
## 9. Exit condition
ETH/BTC loses reclaimed average, BTC dominance breaks higher, or ETH funding becomes crowded without spot confirmation.
## 10. Invalidation condition
ETH/BTC prints a lower low while BTC dominance rises and alt breadth deteriorates.
## 11. Risk controls
Cap exposure by relative-volatility target; reduce confidence when ETH-specific data or pair liquidity is stale.
## 12. Position sizing suggestion
Use beta-adjusted ETH versus BTC sizing for relative signal research. No leverage assumption in MVP.
## 13. Backtest assumptions
Signal is available only after pair bar close. Pair conversion must avoid future BTC/ETH prices.
## 14. Fee / slippage model
Apply fees on both legs. Slippage should reflect two-leg execution and higher of ETH/BTC pair spread or synthetic leg spread.
## 15. Liquidity constraints
Max simulated participation 1% of the smaller leg's 24h volume.
## 16. Failure modes
BTC dominance breakout, ETH catalyst disappointment, pair liquidity gaps, synthetic pair slippage.
## 17. Regime dependency
Works best when BTC consolidates, crypto breadth improves, and ETH-specific catalysts are supportive.
## 18. When not to use
Do not use during BTC impulse breakouts, broad risk-off, stale pair data, or ETH funding stress.
## 19. Expected false positives
Short-lived alt catch-up rallies, one-day ETH news spikes, or illiquid pair moves.
## 20. MVP readiness
Ready: MVP Ready for report/signal use with disclaimer and relative-value framing.
