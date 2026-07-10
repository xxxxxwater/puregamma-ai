from __future__ import annotations

from packages.strategies.base import Strategy, StrategyOutput


class HYPETrendFollowing(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="HYPE trend following",
            asset="HYPE",
            thesis="HYPE can trend when exchange activity, fees, and perp liquidity reinforce each other.",
            trigger="Higher high with funding below stress threshold.",
            entry_condition="Use staged entries after volatility contraction.",
            exit_condition="Exit into vertical extension or sentiment blowoff.",
            invalidation="Loss of 7-day trend support.",
            risk_score=71,
            confidence=0.55,
            timeframe="2-8 days",
            expected_payoff="Convex but fragile trend continuation.",
            required_data_sources=["market", "funding", "protocol_metrics"],
        )
