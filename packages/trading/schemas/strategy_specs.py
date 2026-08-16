from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from packages.trading.domain.enums import ExecutionMode


StrategyType = Literal[
    "DirectionalStrategy",
    "SpreadStrategy",
    "OptionComboStrategy",
    "HedgingStrategy",
]
OutputContract = Literal["TargetPortfolio", "OrderIntent"]


class TargetPortfolioPosition(BaseModel):
    instrument: str
    target_weight: float | None = None
    target_quantity: float | None = None
    max_notional: float | None = None
    reduce_only: bool = False


class TargetPortfolio(BaseModel):
    contract_type: Literal["TargetPortfolio"] = "TargetPortfolio"
    positions: list[TargetPortfolioPosition] = Field(min_length=1)
    rebalance_reason: str = ""
    risk_policy: dict[str, Any] = Field(default_factory=dict)


class OrderIntent(BaseModel):
    contract_type: Literal["OrderIntent"] = "OrderIntent"
    instrument: str
    venue: str = "MOCK"
    side: Literal["BUY", "SELL", "HOLD"]
    quantity: float | None = None
    notional: float | None = None
    order_type: str = "MARKET"
    reduce_only: bool = False
    reason: str = ""
    risk_policy: dict[str, Any] = Field(default_factory=dict)


class ExecutableStrategySpec(BaseModel):
    """Runtime-facing strategy contract.

    Phase 1 supports DirectionalStrategy only, but the strategy_type union
    keeps the interface explicit for the later spread/options/hedging phases.
    """

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    version: int = Field(default=1, ge=1)
    instruments: list[str] = Field(min_length=1)
    venues: list[str] = Field(min_length=1)
    timeframe: str = "1h"
    strategy_type: StrategyType = "DirectionalStrategy"
    strategy_subtype: str = "momentum"
    entry_rules: list[dict[str, Any]] = Field(min_length=1)
    exit_rules: list[dict[str, Any]] = Field(min_length=1)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    feature_sources: list[str] = Field(default_factory=lambda: ["market"])
    sentiment_sources: list[str] = Field(default_factory=list)
    position_sizing: dict[str, Any] = Field(
        default_factory=lambda: {"method": "fixed_fraction", "value": 0.01}
    )
    risk_policy: dict[str, Any] = Field(default_factory=dict)
    output_contract: OutputContract = "OrderIntent"
    order_intent_template: dict[str, Any] = Field(default_factory=dict)
    target_portfolio_template: dict[str, Any] = Field(default_factory=dict)
    activation_supported: bool = True
    activation_phase: int = 1
    max_position: float = Field(default=1.0, gt=0)
    max_notional: float = Field(default=10_000.0, gt=0)
    leverage: float = Field(default=1.0, ge=1.0, le=5.0)
    stop_loss: float | None = Field(default=0.03, gt=0, lt=1)
    take_profit: float | None = Field(default=0.06, gt=0)
    max_daily_loss: float = Field(default=500.0, gt=0)
    max_drawdown: float = Field(default=0.1, gt=0, lt=1)
    max_orders_per_minute: int = Field(default=5, ge=1, le=60)
    order_type: str = "MARKET"
    reduce_only: bool = False
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    backtest_config: dict[str, Any] = Field(default_factory=dict)
    model_version: str = "rules-v1"
    runtime_contract_version: str = "strategy-runtime-v1"
    data_cutoff_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("instruments", "venues")
    @classmethod
    def _non_empty_upper(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value if item.strip()]
        if not normalized:
            raise ValueError("At least one value is required")
        return normalized

    @field_validator("strategy_type", mode="before")
    @classmethod
    def _normalize_strategy_type(cls, value: str) -> str:
        return normalize_strategy_type(value)

    @model_validator(mode="after")
    def _phase_one_guardrails(self) -> "ExecutableStrategySpec":
        if self.execution_mode == ExecutionMode.LIVE:
            raise ValueError("LIVE execution is disabled")
        if self.activation_supported and self.strategy_type != "DirectionalStrategy":
            raise ValueError(
                f"{self.strategy_type} is defined for a future phase and cannot activate yet"
            )
        required_risk = {
            "max_position",
            "max_notional",
            "max_leverage",
            "max_daily_loss",
            "max_drawdown",
            "max_orders_per_minute",
        }
        missing = required_risk - set(self.risk_policy)
        if missing:
            raise ValueError(
                "risk_policy is missing required fields: "
                + ", ".join(sorted(missing))
            )
        if self.output_contract == "OrderIntent" and not self.order_intent_template:
            raise ValueError("OrderIntent strategies require order_intent_template")
        if (
            self.output_contract == "TargetPortfolio"
            and not self.target_portfolio_template
        ):
            raise ValueError(
                "TargetPortfolio strategies require target_portfolio_template"
            )
        return self


_STRATEGY_TYPE_ALIASES = {
    "trend": "DirectionalStrategy",
    "directional": "DirectionalStrategy",
    "momentum": "DirectionalStrategy",
    "breakout": "DirectionalStrategy",
    "cta": "DirectionalStrategy",
    "cta_trend": "DirectionalStrategy",
    "pair": "SpreadStrategy",
    "pairs": "SpreadStrategy",
    "spread": "SpreadStrategy",
    "calendar_spread": "SpreadStrategy",
    "option": "OptionComboStrategy",
    "options": "OptionComboStrategy",
    "option_combo": "OptionComboStrategy",
    "hedge": "HedgingStrategy",
    "hedging": "HedgingStrategy",
}


def normalize_strategy_type(value: str | None) -> str:
    raw = str(value or "DirectionalStrategy").strip()
    if raw in {
        "DirectionalStrategy",
        "SpreadStrategy",
        "OptionComboStrategy",
        "HedgingStrategy",
    }:
        return raw
    return _STRATEGY_TYPE_ALIASES.get(raw.lower(), raw)


def risk_policy_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    existing = dict(payload.get("risk_policy") or {})
    return {
        "max_position": float(
            existing.get("max_position", payload.get("max_position", 1.0))
        ),
        "max_notional": float(
            existing.get("max_notional", payload.get("max_notional", 10_000.0))
        ),
        "max_leverage": float(
            existing.get("max_leverage", payload.get("leverage", 1.0))
        ),
        "max_daily_loss": float(
            existing.get("max_daily_loss", payload.get("max_daily_loss", 500.0))
        ),
        "max_drawdown": float(
            existing.get("max_drawdown", payload.get("max_drawdown", 0.1))
        ),
        "max_orders_per_minute": int(
            existing.get(
                "max_orders_per_minute", payload.get("max_orders_per_minute", 5)
            )
        ),
        "reduce_only": bool(existing.get("reduce_only", payload.get("reduce_only", False))),
        "pause_opening": bool(existing.get("pause_opening", False)),
        "global_kill_switch": bool(existing.get("global_kill_switch", False)),
        "stale_market_blocks_opening": bool(
            existing.get("stale_market_blocks_opening", True)
        ),
        "stale_account_blocks_opening": bool(
            existing.get("stale_account_blocks_opening", True)
        ),
        "unknown_order_blocks_opening": bool(
            existing.get("unknown_order_blocks_opening", True)
        ),
        "reconciliation_required_blocks_opening": bool(
            existing.get("reconciliation_required_blocks_opening", True)
        ),
        **{
            key: value
            for key, value in existing.items()
            if key
            not in {
                "max_position",
                "max_notional",
                "max_leverage",
                "max_daily_loss",
                "max_drawdown",
                "max_orders_per_minute",
                "reduce_only",
                "pause_opening",
                "global_kill_switch",
                "stale_market_blocks_opening",
                "stale_account_blocks_opening",
                "unknown_order_blocks_opening",
                "reconciliation_required_blocks_opening",
            }
        },
    }


def ensure_executable_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["strategy_type"] = normalize_strategy_type(
        normalized.get("strategy_type")
    )
    normalized["risk_policy"] = risk_policy_from_payload(normalized)
    normalized.setdefault("output_contract", "OrderIntent")
    if not normalized.get("order_intent_template"):
        normalized["order_intent_template"] = {
            "contract_type": "OrderIntent",
            "instrument": "{instrument}",
            "venue": "{venue}",
            "side": "{side}",
            "order_type": normalized.get("order_type", "MARKET"),
            "reduce_only": bool(normalized.get("reduce_only", False)),
        }
    if not normalized.get("target_portfolio_template"):
        normalized["target_portfolio_template"] = {}
    normalized.setdefault("activation_supported", True)
    normalized.setdefault("activation_phase", 1)
    spec = ExecutableStrategySpec.model_validate(normalized)
    return spec.model_dump(mode="json")
