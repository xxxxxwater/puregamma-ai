"""Single source of truth for user-facing Credit estimates and settlement."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

MODEL_RATES = {
    "default": (1.0, 0.25, 0.75),
    "gpt-5.6-luna": (2.0, 0.8, 2.5),
}
TOOL_RATES = {"market": 1, "rss": 2, "search_online_sources": 3, "portfolio": 2, "x": 4, "onchain": 5, "deep_research": 6}
TASK_LIMITS = {
    "agent_chat_basic": (2, 30), "agent_market_research": (2, 30), "agent_news_research": (2, 30),
    "agent_portfolio_analysis": (2, 30), "agent_advanced_data": (2, 30), "agent_deep_research": (10, 80),
    "agent_luna_research": (6, 100),
    "default_chat": (2, 30), "default_deep_research": (10, 80),
    "luna_research": (6, 100), "luna_deep_research": (20, 150),
    "daily_market_report": (4, 20), "portfolio_daily_brief": (8, 40),
    "imessage_alert": (2, 2), "telegram_alert": (1, 1), "email_alert": (1, 1),
    "slack_alert": (1, 1),
    "event_report": (5, 20), "sentiment_scan": (8, 40),
    "x_sentiment_scan": (20, 80), "onchain_scan": (12, 80),
    "backtest": (25, 100), "playbook_generation": (30, 100),
    "daily_combined_imessage": (15, 40),
    "deepseek_report_generation": (10, 80),
    "deepseek_playbook_generation": (30, 100),
    "strategy_generation": (5, 40), "strategy_modification": (2, 30),
    "strategy_activation": (5, 40), "runtime_reconciliation": (2, 30),
    "manual_order_preview": (1, 10),
    "portfolio_monitor": (3, 30), "paper_monitor": (3, 30),
    "private_secretary_reply": (20, 20),
}

@dataclass(frozen=True)
class CreditQuote:
    task_type: str
    requested_model: str = "default"
    resolved_model: str = "default"
    input_tokens: int = 0
    output_tokens: int = 0
    attachment_bytes: int = 0
    tool_calls: list[str] = field(default_factory=list)
    selected_data_sources: list[str] = field(default_factory=list)
    async_execution: bool = False
    notification_channel: str | None = None
    credits: int = 0

@dataclass(frozen=True)
class CreditReservation:
    idempotency_key: str
    credits: int

@dataclass(frozen=True)
class CreditSettlement:
    reserved: int
    actual: int
    adjustment: int

@dataclass(frozen=True)
class CreditRefund:
    credits: int
    reason: str

def quote_credits(**kwargs: Any) -> CreditQuote:
    task = kwargs.get("task_type", "default_chat")
    model = str(kwargs.get("resolved_model") or kwargs.get("requested_model") or "default").lower()
    rate = MODEL_RATES.get(model, MODEL_RATES["default"])
    tools = [str(x).lower() for x in kwargs.get("tool_calls", [])]
    sources = [str(x).lower() for x in kwargs.get("selected_data_sources", [])]
    raw = rate[0] + rate[1] * int(kwargs.get("input_tokens", 0)) / 1000 + rate[2] * int(kwargs.get("output_tokens", 0)) / 1000
    raw += sum(TOOL_RATES.get(x, 0) for x in tools + sources)
    raw += ceil(max(0, int(kwargs.get("attachment_bytes", 0))) / 20480)
    if kwargs.get("async_execution"): raw += 1
    channel = kwargs.get("notification_channel")
    if channel in ("imessage", "telegram", "email"): raw += TOOL_RATES.get(channel, 1) if channel != "imessage" else 2
    minimum, maximum = TASK_LIMITS.get(task, (1, 100))
    credits = max(minimum, min(maximum, ceil(raw)))
    return CreditQuote(task_type=task, requested_model=str(kwargs.get("requested_model") or "default"), resolved_model=model,
        input_tokens=int(kwargs.get("input_tokens", 0)), output_tokens=int(kwargs.get("output_tokens", 0)),
        attachment_bytes=int(kwargs.get("attachment_bytes", 0)), tool_calls=tools,
        selected_data_sources=sources, async_execution=bool(kwargs.get("async_execution")),
        notification_channel=channel, credits=credits)
