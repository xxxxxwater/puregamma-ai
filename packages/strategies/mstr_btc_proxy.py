from __future__ import annotations

from packages.strategies.base import Strategy, StrategyOutput


class MSTRBTCProxy(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="MSTR premium / BTC proxy trade",
            asset="MSTR",
            thesis="MSTR can amplify BTC moves, but premium compression is the key risk.",
            trigger="BTC breakout with MSTR premium stable or expanding.",
            entry_condition="Use only when equity market liquidity is supportive.",
            exit_condition="Exit if premium compresses despite BTC strength.",
            invalidation="BTC loses breakout or MSTR underperforms BTC materially.",
            risk_score=67,
            confidence=0.57,
            timeframe="1-3 weeks",
            expected_payoff="Levered BTC proxy upside with equity-specific risk.",
            required_data_sources=["BTC", "equity_price", "premium_discount"],
        )
