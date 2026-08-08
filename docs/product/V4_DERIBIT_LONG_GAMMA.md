# PureGamma AI V4: Deribit Options and Long Gamma Discovery
## Product goal
V4 adds a Deribit options intelligence domain. It identifies and explains long
gamma research opportunities from option surfaces, portfolio exposures, RSS events,
and user conversations. Research output is evidence-backed and does not imply a
guaranteed return.
## New domain modules
- Deribit market-data provider: instruments, order books, trades, index, mark,
  volatility index, expiries, strikes, open interest, and Greeks.
- Options normalization: option symbol, underlying, expiry, strike, call/put,
  implied volatility, delta, gamma, vega, theta, bid/ask, liquidity, and timestamp.
- Volatility surface: term structure, skew, smile, realized versus implied volatility.
- Portfolio Greeks: aggregate delta, gamma, vega, theta, scenario PnL, and expiry risk.
- Long Gamma discovery: catalyst window, implied/realized spread, liquidity,
  breakeven move, theta budget, convexity, and event-risk filters.
- Agent tools: explain surface changes, find candidate structures, compare evidence,
  and cite Deribit/RSS source timestamps.
## AI boundary
AI ranks and explains candidates; deterministic option math calculates Greeks,
payoff, breakevens, and scenarios. The model must not invent prices or Greeks.
Every recommendation-like output includes assumptions, maximum premium at risk,
liquidity warnings, expiry risk, evidence links, and data freshness.
## Delivery phases
1. Read-only Deribit public market data and normalized option chain.
2. Surface, Greeks, scenario engine, and dashboard.
3. Agent/RSS catalyst discovery and Telegram/iMessage alerts.
4. Deribit testnet execution adapter with explicit confirmation and hard limits.
5. Production adapter only after V3 execution release gates pass.
