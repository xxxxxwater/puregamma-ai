from __future__ import annotations

from packages.strategies.base import Strategy, StrategyOutput


class ETHBTCRotation(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="ETH/BTC rotation",
            asset="ETH",
            thesis="ETH outperforms when BTC volatility cools and on-chain risk appetite broadens.",
            trigger="ETH/BTC reclaims the 20-day moving average.",
            entry_condition="Prefer rotation after BTC range compression.",
            exit_condition="Exit if ETH/BTC loses reclaimed average.",
            invalidation="BTC dominance breakout with ETH/BTC lower low.",
            risk_score=52,
            confidence=0.61,
            timeframe="1-4 weeks",
            expected_payoff="Moderate beta catch-up versus BTC.",
            required_data_sources=["market", "ETH/BTC", "onchain"],
        )
