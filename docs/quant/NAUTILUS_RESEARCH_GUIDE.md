# Nautilus Research Guide
NautilusTrader is a target research, backtest, and paper-trading layer. PureGamma must not enable live trading in MVP.
## Allowed
- Research backtests
- Paper trading simulations
- Timestamp-preserving data bridges
- Standardized result parsing
- Metrics inspection
## Not Allowed
- Live order routing
- Auto execution
- User-facing performance claims from mock runs
- Labeling mock engine output as Nautilus live results
- Treating paper trading as real trading
## Data Bridge Rules
- OHLCV bars keep exchange timestamp, bar close timestamp, and ingestion timestamp.
- Funding keeps funding interval start/end and publish time.
- OI keeps provider timestamp.
- Events keep publication timestamp and ingestion timestamp.
- Strategy bridge must not drop timestamps or timezone information.
## Result Rules
Backtest output must include total return, Sharpe, drawdown, win rate, trade count, turnover, exposure time, tail risk, mode, engine, and live-trading status.
