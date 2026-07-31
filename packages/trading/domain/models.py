from __future__ import annotations

from dataclasses import dataclass

from packages.trading.domain.enums import ExecutionMode


@dataclass(frozen=True)
class StrategyPermission:
    user_id: str
    account_id: str
    allowed_modes: tuple[ExecutionMode, ...] = (
        ExecutionMode.BACKTEST,
        ExecutionMode.PAPER,
        ExecutionMode.SHADOW,
    )
    can_submit_paper_orders: bool = True
    can_submit_live_orders: bool = False
    can_withdraw: bool = False
    can_transfer: bool = False

    def allows(self, mode: ExecutionMode | str) -> bool:
        resolved = ExecutionMode(str(mode).upper().split(".")[-1])
        return resolved in self.allowed_modes and resolved != ExecutionMode.LIVE
