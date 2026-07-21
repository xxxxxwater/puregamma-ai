"""Declarative strategy specification for the backtest lab.

The spec contract mirrors how a NautilusTrader ``Strategy`` is wired:
- ``daily`` strategies evaluate one instrument per ``on_bar`` (trend/mean-reversion).
- ``cross_sectional`` strategies rank the BTC/ETH universe per rebalance bar and
  hold a long/short basket until the next rebalance (market-neutral style).
Signals are computed strictly on data available before the current bar
(no look-ahead), and positions apply to the next bar's return.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_ASSETS = ("BTC", "ETH")


class StrategySpec(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    mode: Literal["daily", "cross_sectional"]
    signal: Literal["momentum", "mean_reversion", "breakout", "relative_strength"]
    assets: list[str] = Field(min_length=1, max_length=2)
    fast_window: int = Field(default=12, ge=2, le=120)
    slow_window: int = Field(default=26, ge=3, le=250)
    entry_threshold: float = Field(default=0.0, ge=0.0, le=0.5)
    exit_threshold: float = Field(default=0.0, ge=0.0, le=0.5)
    rebalance_days: int = Field(default=5, ge=1, le=60)
    long_short: bool = Field(default=False)
    max_position: float = Field(default=1.0, gt=0.0, le=1.0)
    fee_bps: float = Field(default=10.0, ge=0.0, le=100.0)
    stop_loss_pct: float | None = Field(default=None, ge=0.01, le=0.5)
    thesis: str = Field(default="", max_length=600)

    @field_validator("assets")
    @classmethod
    def _assets_supported(cls, value: list[str]) -> list[str]:
        normalized = [item.upper().strip() for item in value if item.strip()]
        unsupported = [item for item in normalized if item not in SUPPORTED_ASSETS]
        if unsupported:
            raise ValueError(f"unsupported assets: {', '.join(unsupported)}")
        return normalized

    @model_validator(mode="after")
    def _windows_ordered(self) -> "StrategySpec":
        if self.slow_window <= self.fast_window:
            raise ValueError("slow_window must be greater than fast_window")
        if self.mode == "cross_sectional" and len(self.assets) < 2:
            raise ValueError("cross_sectional mode requires both BTC and ETH")
        return self


DEFAULT_SPEC = StrategySpec(
    name="BTC/ETH daily momentum baseline",
    mode="daily",
    signal="momentum",
    assets=["BTC", "ETH"],
    fast_window=12,
    slow_window=26,
    thesis="Baseline daily trend-following over the shared three-year dataset.",
)


def parse_spec(payload: dict) -> StrategySpec:
    return StrategySpec.model_validate(payload)
