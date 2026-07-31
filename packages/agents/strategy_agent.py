from __future__ import annotations

from packages.strategies.registry import generate_playbooks


class StrategyAgent:
    def playbooks(self) -> list[dict]:
        return generate_playbooks()
