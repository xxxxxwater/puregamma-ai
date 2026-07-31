from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyOutput:
    strategy_name: str
    asset: str
    thesis: str
    trigger: str
    entry_condition: str
    exit_condition: str
    invalidation: str
    risk_score: int
    confidence: float
    timeframe: str
    expected_payoff: str
    required_data_sources: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class Strategy(ABC):
    @abstractmethod
    def generate(self) -> StrategyOutput:
        raise NotImplementedError
