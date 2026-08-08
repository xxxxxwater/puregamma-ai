# Agent Strategy Output Rules
Strategy Agent, Report Writer Agent, and Risk Agent must follow these constraints.
## Confidence Rules
1. Low-quality data cannot generate high confidence.
2. Missing data must lower confidence.
3. If regime does not match, mark the strategy inactive.
4. KOL sentiment cannot independently trigger a strategy.
5. Mock or insufficient backtests cap confidence.
## Risk Rules
1. High risk must be displayed before expected payoff.
2. Portfolio-aware output must account for concentration.
3. Correlated exposures must be disclosed.
4. Data quality risk must be visible when price, funding, OI, or event data is stale.
## Language Rules
1. Expected payoff may be described only as a scenario.
2. Agents must not promise returns.
3. Research-only strategies cannot use actionable wording such as buy, sell, enter, exit, long, or short.
4. Do not launch strategies must not appear as user-facing signals.
5. Paper trading must not be described as real trading.
6. Mock backtests must be labeled mock.
## Readiness Rules
- MVP Ready: may appear in report/signal surfaces with disclaimer and risk controls.
- Research-only: may appear as observation only.
- Enterprise-only: may appear only behind enterprise controls and data agreements.
- Do not launch: internal only.
