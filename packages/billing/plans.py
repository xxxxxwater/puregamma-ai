from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    monthly_price: float | None
    monthly_credits: int
    agent_daily_runs: int
    agent_concurrent_runs: int
    max_portfolios: int
    max_daily_reports: int
    max_alerts_per_month: int
    allowed_data_sources: tuple[str, ...]
    notification_channels: tuple[str, ...]
    backtest_tier: str
    monitoring_tier: str
    queue_priority: int
    private_playbooks: bool
    imessage_enabled: bool
    high_cost_enabled: bool


PLANS: dict[str, Plan] = {
    "Free": Plan(
        name="Free",
        monthly_price=0.0,
        monthly_credits=30,
        agent_daily_runs=5, agent_concurrent_runs=1, max_portfolios=0,
        max_daily_reports=1,
        max_alerts_per_month=10,
        allowed_data_sources=("market", "rss"),
        notification_channels=("email",),
        backtest_tier="none", monitoring_tier="basic", queue_priority=0, private_playbooks=False, imessage_enabled=False,
        high_cost_enabled=False,
    ),
    "Pro": Plan(
        name="Pro",
        monthly_price=29.9,
        monthly_credits=1000,
        agent_daily_runs=50, agent_concurrent_runs=2, max_portfolios=1,
        max_daily_reports=1,
        max_alerts_per_month=100,
        allowed_data_sources=("market", "rss", "fintwit", "portfolio", "options"),
        notification_channels=("telegram", "email"),
        backtest_tier="basic", monitoring_tier="standard", queue_priority=0, private_playbooks=False, imessage_enabled=False,
        high_cost_enabled=True,
    ),
    "Max": Plan(
        name="Max",
        monthly_price=199.0,
        monthly_credits=10000,
        agent_daily_runs=200, agent_concurrent_runs=4, max_portfolios=5,
        max_daily_reports=5,
        max_alerts_per_month=1000,
        allowed_data_sources=("market", "rss", "fintwit", "portfolio", "options", "x", "x-twitter", "onchain", "coinglass", "glassnode"),
        notification_channels=("telegram", "slack", "email", "imessage"),
        backtest_tier="advanced", monitoring_tier="high_frequency", queue_priority=0, private_playbooks=True, imessage_enabled=True,
        high_cost_enabled=True,
    ),
    "Enterprise": Plan(
        name="Enterprise",
        monthly_price=None,
        monthly_credits=50000,
        agent_daily_runs=1000, agent_concurrent_runs=10, max_portfolios=100,
        max_daily_reports=100,
        max_alerts_per_month=10000,
        allowed_data_sources=("all",),
        notification_channels=("telegram", "slack", "email", "imessage"),
        backtest_tier="advanced", monitoring_tier="custom", queue_priority=0, private_playbooks=True, imessage_enabled=True,
        high_cost_enabled=True,
    ),
}


def get_plan(name: str) -> Plan:
    return PLANS.get(name, PLANS["Free"])
