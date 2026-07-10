# Backtesting Assumptions

Backtests are research estimates, not promises. PureGamma must label mock engine output as mock and must not present it as NautilusTrader live or production performance.

## Data Assumptions

- OHLCV is available only after bar close.
- Funding and OI must be aligned to their publication timestamp, not the later ingestion timestamp.
- Liquidation data must use the exchange/provider timestamp.
- News, RSS, Bloomberg, X, and KOL events must use publication timestamps.
- Corporate/equity data for MSTR must respect market sessions and delayed data rules.

## Execution Assumptions

- Entry and exit prices use conservative next-bar or next-available quotes.
- Fees are charged on notional.
- Slippage increases with volatility, spread, and order size versus daily volume.
- Liquidity caps limit simulated participation.
- Funding, borrow, and carry costs must be included when relevant.
- No strategy may assume infinite fills at close.

## Validation Assumptions

- Use train, validation, and out-of-sample periods.
- Show parameter grids, not only best results.
- Report drawdown, tail loss, turnover, trade count, and exposure time.
- Compare performance across risk-on, risk-off, high-funding, and low-liquidity regimes.
- Include negative controls where possible.
