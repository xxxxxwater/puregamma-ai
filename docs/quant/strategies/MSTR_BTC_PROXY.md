# MSTR Premium / BTC Proxy Trade
## 1. Strategy objective
Study whether MSTR offers levered BTC proxy exposure when BTC trends and MSTR premium is stable or expanding.
## 2. Target market
US equity MSTR and BTC spot/perp reference markets.
## 3. Asset universe
MSTR, BTC.
## 4. Time horizon
1-3 weeks.
## 5. Required data
MSTR equity OHLCV, BTC OHLCV, MSTR premium/discount estimate, equity market regime, borrow/short availability if modeling hedges.
## 6. Signal inputs
BTC trend, MSTR/BTC beta, premium change, equity liquidity, equity index regime, realized volatility.
## 7. Signal formula
`raw_score = btc_trend * 0.25 + mstr_relative_strength * 0.20 + premium_stability * 0.20 + equity_liquidity * 0.15 - premium_compression_risk * 0.10 - equity_risk_off * 0.10`
## 8. Entry condition
Research signal activates when BTC breaks out and MSTR premium is stable or expanding after equity market open.
## 9. Exit condition
Premium compresses despite BTC strength, MSTR underperforms materially, or equity risk regime deteriorates.
## 10. Invalidation condition
BTC loses breakout, premium data is stale, or MSTR-specific news changes balance-sheet risk.
## 11. Risk controls
Equity session handling, single-name concentration cap, premium data quality penalty, no leverage assumption.
## 12. Position sizing suggestion
Beta-adjusted sizing relative to BTC proxy exposure. Cap by equity liquidity and portfolio concentration.
## 13. Backtest assumptions
Align BTC 24/7 data with MSTR market hours. Avoid using after-hours equity information before it was tradable.
## 14. Fee / slippage model
Include equity commissions/spread, BTC proxy slippage, borrow costs if hedged, and market-session gap risk.
## 15. Liquidity constraints
Max simulated participation 1% of MSTR daily dollar volume and tighter during high-volatility sessions.
## 16. Failure modes
Premium compression, equity risk-off, company-specific financing event, BTC gap outside equity hours.
## 17. Regime dependency
Works only when BTC trend and equity liquidity are supportive.
## 18. When not to use
Do not use when premium model is stale, equity market is stressed, or BTC moves mainly outside equity hours.
## 19. Expected false positives
BTC breakout that does not translate to MSTR due to premium compression or equity index selloff.
## 20. MVP readiness
Research only: useful for cross-market notes, not high-confidence MVP signals.
