"""Single source of truth for user-facing Credit estimates and settlement."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

#: Credit rates per model: (base per call, per 1k input tokens, per 1k output
#: tokens). These are product-approved numbers and the only rates in code.
#: "default" is the platform default route (the model the Agent's "default"
#: selection resolves to), not a fallback for unknown selectable models.
#: Any other selectable Agent model must have an explicit rate here or in the
#: deployment's AGENT_MODEL_CREDIT_RATES; without one it is not offered and
#: quote/start refuse it (see ``ModelPricingNotConfigured``).
MODEL_RATES = {
    "default": (1.0, 0.25, 0.75),
    "gpt-5.6-luna": (2.0, 0.8, 2.5),
}
TOOL_RATES = {"market": 1, "rss": 2, "portfolio": 2, "x": 4, "onchain": 5, "deep_research": 6}
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
    "backtest": (50, 50), "backtest_export": (50, 50), "playbook_generation": (30, 100),
    "research_run": (20, 60),
    "daily_combined_imessage": (15, 40),
    "deepseek_report_generation": (10, 80),
    "deepseek_playbook_generation": (30, 100),
    "strategy_generation": (5, 40), "strategy_modification": (2, 30),
    "strategy_activation": (5, 40), "runtime_reconciliation": (2, 30),
    "manual_order_preview": (1, 10),
    "portfolio_monitor": (3, 30), "paper_monitor": (3, 30),
    "private_secretary_reply": (20, 20),
    "secretary_voice": (2, 8), "secretary_transcribe": (2, 8),
}

ModelRate = tuple[float, float, float]


class ModelPricingNotConfigured(LookupError):
    """A selectable model has no explicit credit rate; refuse, never default."""


def parse_model_rates(raw: str | None) -> dict[str, ModelRate]:
    """Parse ``id=base/input_per_1k/output_per_1k`` entries, comma separated.

    A malformed or negative entry is dropped, which leaves that model unpriced
    and therefore refused: a typo must not turn into a guessed price.
    """
    rates: dict[str, ModelRate] = {}
    for item in (raw or "").split(","):
        identifier, separator, value = item.strip().partition("=")
        parts = value.split("/")
        if not separator or not identifier.strip() or len(parts) != 3:
            continue
        try:
            numbers = tuple(float(part) for part in parts)
        except ValueError:
            continue
        if any(number < 0 or number != number or number == float("inf") for number in numbers):
            continue
        rates[identifier.strip().lower()] = numbers  # type: ignore[assignment]
    return rates


def model_rate_table(extra: dict[str, ModelRate] | None = None) -> dict[str, ModelRate]:
    """The code rates overlaid with deployment-configured rates."""
    return {**MODEL_RATES, **{key.lower(): value for key, value in (extra or {}).items()}}


def explicit_model_rate(model: str, extra: dict[str, ModelRate] | None = None) -> ModelRate | None:
    """The explicit rate for a selectable model id, or None when unpriced."""
    key = str(model or "").lower()
    if not key or key == "default":
        return None
    return model_rate_table(extra).get(key)


#: The "typical turn" the model menu estimates: a short answer with no paid
#: data source (low) and a long answer that reads two paid sources (high).
#: Both go through ``quote_credits``, so the menu and billing share one formula.
TYPICAL_TURN_LOW = {"input_tokens": 300, "output_tokens": 500, "tool_calls": []}
TYPICAL_TURN_HIGH = {"input_tokens": 2000, "output_tokens": 2000, "tool_calls": ["market", "rss"]}


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
    rates = model_rate_table(kwargs.get("model_rates"))
    if kwargs.get("strict_model_rate"):
        # A user-selected model is priced by its selection id, so the quote,
        # the reservation and the settlement use one rate even when the
        # provider echoes a dated snapshot name. No rate means no charge path.
        selected = str(kwargs.get("requested_model") or "").lower()
        if selected not in rates or selected == "default":
            raise ModelPricingNotConfigured(selected or model)
        rate = rates[selected]
    else:
        rate = rates.get(model, rates["default"])
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


def typical_turn_estimate(task_type: str, **model_kwargs: Any) -> tuple[int, int]:
    """Credits for a low and a high typical turn, via the billing formula."""
    low = quote_credits(task_type=task_type, **model_kwargs, **TYPICAL_TURN_LOW).credits
    high = quote_credits(task_type=task_type, **model_kwargs, **TYPICAL_TURN_HIGH).credits
    return low, max(low, high)
