from __future__ import annotations

from packages.strategies.base import Strategy, StrategyOutput


class BTCMomentumBreakout(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="BTC momentum breakout",
            asset="BTC",
            thesis="BTC leadership remains the cleanest expression of crypto beta when spot demand and ETF flow are stable.",
            trigger="Daily close above prior range high with volume expansion.",
            entry_condition="Enter only after breakout holds for one 4h candle.",
            exit_condition="Take partials into stretched funding or failed continuation.",
            invalidation="Back below breakout level on rising volume.",
            risk_score=46,
            confidence=0.68,
            timeframe="1-3 weeks",
            expected_payoff="Asymmetric upside if BTC dominance expands.",
            required_data_sources=["market", "funding", "ETF flow"],
        )
