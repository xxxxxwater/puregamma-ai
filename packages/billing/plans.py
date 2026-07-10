from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    monthly_price: float | None
    monthly_credits: int
    max_daily_reports: int
    max_alerts: int
    allowed_data_sources: tuple[str, ...]
    channels: tuple[str, ...]
    high_cost_enabled: bool


PLANS: dict[str, Plan] = {
    "Free": Plan(
        name="Free",
        monthly_price=0.0,
        monthly_credits=30,
        max_daily_reports=1,
        max_alerts=0,
        allowed_data_sources=("mock", "delayed_market"),
        channels=("email",),
        high_cost_enabled=False,
    ),
    "Pro": Plan(
        name="Pro",
        monthly_price=29.9,
        monthly_credits=1000,
        max_daily_reports=1,
        max_alerts=20,
        allowed_data_sources=("market", "rss", "basic_backtest"),
        channels=("telegram", "email"),
        high_cost_enabled=True,
    ),
    "Max": Plan(
        name="Max",
        monthly_price=199.0,
        monthly_credits=10000,
        max_daily_reports=5,
        max_alerts=500,
        allowed_data_sources=("market", "rss", "x", "onchain", "coinglass", "glassnode", "advanced_backtest"),
        channels=("telegram", "slack", "email", "imessage"),
        high_cost_enabled=True,
    ),
    "Enterprise": Plan(
        name="Enterprise",
        monthly_price=None,
        monthly_credits=50000,
        max_daily_reports=100,
        max_alerts=10000,
        allowed_data_sources=("all", "api", "custom", "private_deployment"),
        channels=("telegram", "slack", "email", "imessage"),
        high_cost_enabled=True,
    ),
}


def get_plan(name: str) -> Plan:
    return PLANS.get(name, PLANS["Free"])
