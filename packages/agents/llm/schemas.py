from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    status: str = "success"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Chain-of-thought tokens reported by the provider. These are already
    # included in ``completion_tokens``; they are carried separately for
    # observability and must never be added to it when costing a request.
    reasoning_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cache_hit: bool = False
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMStreamChunk:
    delta: str = ""
    done: bool = False
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
