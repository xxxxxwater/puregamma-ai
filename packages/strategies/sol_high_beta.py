from __future__ import annotations

from packages.strategies.base import Strategy, StrategyOutput


class SOLHighBetaRotation(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="SOL high beta rotation",
            asset="SOL",
            thesis="SOL tends to lead high beta rotations when market breadth improves.",
            trigger="SOL relative strength versus ETH turns positive for two sessions.",
            entry_condition="Enter on pullback that holds prior breakout level.",
            exit_condition="Reduce when funding and perp basis become crowded.",
            invalidation="Failed retest with broad alt weakness.",
            risk_score=64,
            confidence=0.58,
            timeframe="3-10 days",
            expected_payoff="High beta upside with higher drawdown risk.",
            required_data_sources=["market", "funding", "open_interest"],
        )
