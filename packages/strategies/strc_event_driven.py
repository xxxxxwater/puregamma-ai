from __future__ import annotations

from packages.strategies.base import Strategy, StrategyOutput


class STRCEventDrivenCreditTrade(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="STRC event-driven credit trade",
            asset="STRC",
            thesis="STRC is best treated as event-driven credit exposure rather than directional crypto beta.",
            trigger="Credit spread widens without matching deterioration in BTC collateral narrative.",
            entry_condition="Enter after event risk is identified and liquidity is adequate.",
            exit_condition="Exit once spread normalizes or issuer risk rises.",
            invalidation="Issuer-specific stress, liquidity break, or BTC collateral shock.",
            risk_score=49,
            confidence=0.52,
            timeframe="2-6 weeks",
            expected_payoff="Carry plus spread compression, capped upside.",
            required_data_sources=["credit", "issuer_events", "BTC"],
        )
