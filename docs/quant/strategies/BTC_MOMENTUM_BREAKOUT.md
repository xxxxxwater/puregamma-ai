# BTC Momentum Breakout
## 1. Strategy objective
Capture BTC trend continuation after a confirmed range breakout while avoiding crowded funding and failed-breakout traps.
## 2. Target market
Spot and perpetual BTC markets. MVP output is research-only signal/report language; no execution.
## 3. Asset universe
BTC-USD spot/perp proxies, preferably from high-liquidity venues.
## 4. Time horizon
1-3 weeks.
## 5. Required data
BTC OHLCV, volume, funding, open interest, liquidation estimate, BTC dominance, ETF flow proxy if available.
## 6. Signal inputs
20-day range high, close price, volume versus 30-day median, funding z-score, OI/volume, realized volatility.
## 7. Signal formula
`raw_score = breakout_strength * 0.35 + volume_confirmation * 0.20 + trend_slope * 0.15 - funding_crowding * 0.15 - oi_crowding * 0.10 - volatility_stress * 0.05`
`normalized_score = clamp(raw_score, 0, 1)`.
## 8. Entry condition
Signal activates only after bar close above the prior 20-day high with volume above median and funding below stress threshold.
## 9. Exit condition
Close back inside range, funding becomes crowded, trailing ATR stop, or market regime flips risk-off.
## 10. Invalidation condition
Breakout level is lost on rising volume or BTC dominance fails while crypto breadth weakens.
## 11. Risk controls
Max research allocation assumption 10-20% of strategy risk budget, no leverage in MVP, risk score must be shown.
## 12. Position sizing suggestion
Volatility-targeted notional capped by liquidity and portfolio concentration. Use smaller size when risk score exceeds 60.
## 13. Backtest assumptions
Signal available after daily bar close. Entry at next bar open or conservative VWAP proxy. Funding and OI aligned to publication timestamps.
## 14. Fee / slippage model
Spot fee 5-20 bps, perp fee 2-10 bps, slippage max of spread proxy and volatility/order-size participation model.
## 15. Liquidity constraints
Max simulated participation 1% of 24h volume and lower during volatility shocks.
## 16. Failure modes
False breakout, ETF flow reversal, funding squeeze, macro risk-off, stale OI/funding data.
## 17. Regime dependency
Best in risk-on or neutral regimes with BTC leadership and contained leverage.
## 18. When not to use
Do not use when funding is crowded, BTC volatility is disorderly, data is stale, or macro regime is risk-off.
## 19. Expected false positives
Breakouts caused by short-term liquidation cascades, weekend liquidity, or news spikes without spot follow-through.
## 20. MVP readiness
Ready: MVP Ready for report/signal surfaces with disclaimer, risk score, and invalidation. Not ready for live trading.
