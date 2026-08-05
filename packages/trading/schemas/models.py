from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from packages.trading.domain.enums import ExecutionMode, IntentType


class StrategyDraft(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    version: int = Field(default=1, ge=1)
    instruments: list[str] = Field(default_factory=lambda: ["BTCUSDT"])
    venues: list[str] = Field(default_factory=lambda: ["MOCK"])
    timeframe: str = "1h"
    strategy_type: str = "DirectionalStrategy"
    strategy_subtype: str = "momentum"
    entry_rules: list[dict[str, Any]] = Field(default_factory=list)
    exit_rules: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    feature_sources: list[str] = Field(default_factory=lambda: ["market"])
    sentiment_sources: list[str] = Field(default_factory=list)
    position_sizing: dict[str, Any] = Field(
        default_factory=lambda: {"method": "fixed_fraction", "value": 0.01}
    )
    output_contract: str = "OrderIntent"
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
    backtest_config: dict[str, Any] = Field(
        default_factory=lambda: {"lookback_days": 90, "fees_bps": 10, "slippage_bps": 5}
    )
    risk_policy: dict[str, Any] = Field(default_factory=dict)
    model_version: str = "rules-v1"
    runtime_contract_version: str = "strategy-runtime-v1"
    data_cutoff_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("instruments", "venues")
    @classmethod
    def non_empty_upper(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value if item.strip()]
        if not normalized:
            raise ValueError("At least one value is required")
        return normalized


class StrategyIntentSchema(BaseModel):
    intent_type: IntentType
    user_id: str
    conversation_id: str | None = None
    strategy_id: str
    strategy_version: int
    instrument: str | None = None
    venue: str = "MOCK"
    direction: str | None = None
    target_position: float | None = None
    quantity: float | None = None
    notional: float | None = None
    leverage: float = Field(default=1.0, ge=1, le=5)
    order_type: str = "MARKET"
    risk_limits: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    idempotency_key: str
    confirmation_required: bool = True
    approval_status: str = "PENDING"
    expires_at: datetime


class OrderPreview(BaseModel):
    account_id: str
    strategy_id: str | None = None
    instrument: str
    venue: str = "MOCK"
    direction: str
    quantity: float = Field(gt=0)
    notional: float = Field(gt=0)
    leverage: float = Field(default=1, ge=1, le=5)
    order_type: str = "MARKET"
    reduce_only: bool = False
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    idempotency_key: str
