from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy.orm import Session

from packages.agents.llm.provider_factory import get_llm_provider


@dataclass
class LLMCall:
    provider: str
    model: str
    purpose: str
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime


LLM_CALL_LOG: list[LLMCall] = []


class LLMClient:
    """Backward-compatible facade over the provider factory."""

    def __init__(self):
        self.provider = get_llm_provider()

    def complete(self, purpose: str, prompt: str, *, locale: str = "en", user_id: str | None = None, db: Session | None = None) -> str:
        completion = self.provider.complete(prompt, task_type=purpose, locale=locale, user_id=user_id, db=db)
        self.log_call(purpose, prompt, completion)
        return completion

    def log_call(self, purpose: str, prompt: str, completion: str) -> None:
        LLM_CALL_LOG.append(
            LLMCall(
                provider=self.provider.provider_name,
                model=self.provider.model,
                purpose=purpose,
                prompt_tokens=max(1, len(prompt.split())),
                completion_tokens=max(1, len(completion.split())),
                created_at=datetime.now(timezone.utc),
            )
        )
