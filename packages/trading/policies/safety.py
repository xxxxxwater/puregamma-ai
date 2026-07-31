from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from packages.trading.domain.enums import ExecutionMode


class LiveExecutionDenied(RuntimeError):
    pass


def assert_execution_mode_allowed(mode: ExecutionMode | str) -> ExecutionMode:
    resolved = ExecutionMode(str(mode).upper().split(".")[-1])
    if resolved == ExecutionMode.LIVE:
        raise LiveExecutionDenied("LIVE execution is disabled in this release")
    if (
        os.getenv("NAUTILUS_LIVE_TRADING_ENABLED", "false").lower() == "true"
        or os.getenv("NAUTILUS_ALLOW_LIVE_ORDER", "false").lower() == "true"
    ):
        raise LiveExecutionDenied("Live-trading environment flags must remain false")
    if (
        os.getenv("NAUTILUS_ALLOW_WITHDRAWAL", "false").lower() == "true"
        or os.getenv("NAUTILUS_ALLOW_TRANSFER", "false").lower() == "true"
    ):
        raise LiveExecutionDenied("Withdrawal and transfer capabilities are forbidden")
    return resolved


def strategy_config_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def confirmation_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
