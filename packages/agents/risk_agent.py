from __future__ import annotations

from packages.risk.scoring import portfolio_risk_summary, risk_score_for_quote


class RiskAgent:
    def score_quotes(self, quotes: list) -> dict[str, int]:
        return {quote.symbol: risk_score_for_quote(quote) for quote in quotes}

    def summary(self, quotes: list) -> str:
        return portfolio_risk_summary(quotes)
