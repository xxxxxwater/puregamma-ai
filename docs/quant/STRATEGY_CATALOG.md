# Strategy Catalog

| Strategy | Readiness | Product Use | Reason |
| --- | --- | --- | --- |
| BTC momentum breakout | MVP Ready | Report/signal with disclaimer | Liquid market, explainable trend signal, feasible mock-to-real backtest path. |
| ETH/BTC rotation | MVP Ready | Report/signal with disclaimer | Relative-strength setup with clear pair data and regime dependency. |
| SOL high beta rotation | Research-only | Research observation | Higher beta and stronger funding/liquidation sensitivity require more robust data. |
| SOL/HYPE high beta rotation | Research-only | Research observation | HYPE liquidity, venue coverage, and survivorship risk limit confidence. |
| HYPE trend following | Research-only | Research observation | Trend logic is clear, but HYPE data quality and liquidity risk are high. |
| MSTR premium / BTC proxy trade | Research-only | Cross-market note | Needs reliable premium model, equity-session handling, borrow/tax assumptions. |
| STRC event-driven credit trade | Do not launch | Internal research only | Needs licensed credit/issuer data and event-risk review before user-facing output. |
| basis funding arbitrage | Enterprise-only | Enterprise research after controls | Requires order book, venue, borrow, margin, and counterparty controls. |
| cross-market crypto / equity risk regime | Research-only | Regime filter only | Useful as context, but not a standalone strategy trigger. |

## MVP Ready

BTC momentum breakout and ETH/BTC rotation are the only MVP-ready strategies. They can support report and signal surfaces, but only as research signals with confidence, risk, invalidation, and "not financial advice" language.

## Research-only

SOL high beta, SOL/HYPE rotation, HYPE trend following, MSTR/BTC proxy, and cross-market regime are useful for research context. They must not generate high-confidence or actionable wording until timestamped data, liquidity filters, and out-of-sample tests are stronger.

## Enterprise-only

Basis funding arbitrage is not appropriate for general MVP because it requires venue-specific order books, borrow, funding settlement, margin, and counterparty risk controls.

## Do Not Launch

STRC event-driven credit should not be launched until PureGamma has reliable credit spreads, issuer-event data, legal review, and liquidity validation.
