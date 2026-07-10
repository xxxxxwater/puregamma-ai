from __future__ import annotations

from packages.agents.market_data_agent import MarketDataAgent
from packages.agents.risk_agent import RiskAgent
from packages.agents.sentiment_agent import SentimentAgent
from packages.agents.strategy_agent import StrategyAgent


class ResearchAgent:
    def __init__(self):
        self.market = MarketDataAgent()
        self.sentiment = SentimentAgent()
        self.risk = RiskAgent()
        self.strategy = StrategyAgent()

    def research(self, assets: list[str]) -> dict:
        regime, quotes = self.market.snapshot(assets)
        return {
            "market_regime": regime,
            "quotes": quotes,
            "sentiment": self.sentiment.aggregate(assets),
            "risk_scores": self.risk.score_quotes(quotes),
            "risk_summary": self.risk.summary(quotes),
            "playbooks": self.strategy.playbooks(),
        }
