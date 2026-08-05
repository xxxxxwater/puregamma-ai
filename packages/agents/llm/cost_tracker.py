from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from packages.database.models import LLMCallLog


ROOT = Path(__file__).resolve().parents[3]
COSTS_PATH = ROOT / "config" / "llm_costs.yaml"
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[^,\s]+"),
    re.compile(r"\+?\d[\d\-\s().]{8,}\d"),
]


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:500]


@lru_cache
def load_costs() -> dict[str, Any]:
    if not COSTS_PATH.exists():
        return {"providers": {}}
    with COSTS_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"providers": {}}


def estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    config = load_costs().get("providers", {}).get(provider, {})
    if not config.get("cost_estimation_enabled"):
        return 0.0
    input_rate = float(config.get("input_per_1m_tokens_usd") or 0.0)
    output_rate = float(config.get("output_per_1m_tokens_usd") or 0.0)
    return round((prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate, 8)


def log_llm_call(
    db: Session | None,
    *,
    user_id: str | None,
    provider: str,
    model: str,
    task_type: str,
    locale: str,
    prompt: str,
    prompt_tokens: int,
    completion_tokens: int,
    status: str,
    cache_hit: bool = False,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    if db is None:
        return
    total_tokens = prompt_tokens + completion_tokens
    db.add(
        LLMCallLog(
            user_id=user_id,
            provider=provider,
            model=model,
            task_type=task_type,
            locale=locale,
            prompt_summary=redact_text(prompt),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_cost(provider, prompt_tokens, completion_tokens),
            cache_hit=cache_hit,
            status=status,
            error_message=redact_text(error_message or "") if error_message else None,
            latency_ms=latency_ms,
        )
    )
    db.flush()
