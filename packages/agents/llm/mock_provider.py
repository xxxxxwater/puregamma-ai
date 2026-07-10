from __future__ import annotations

from sqlalchemy.orm import Session

from packages.agents.llm.base import LLMProvider
from packages.agents.llm.cost_tracker import log_llm_call
from packages.agents.llm.schemas import ChatMessage, LLMResponse


class MockLLMProvider(LLMProvider):
    provider_name = "mock"
    model = "mock-model"

    def __init__(self, *, status: str = "success", last_error: str | None = None):
        self.configured = True
        self.status = status
        self.last_error = last_error

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        task_type: str,
        locale: str = "en",
        user_id: str | None = None,
        db: Session | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        prompt = "\n".join(message.content for message in messages)
        if response_format == "json_object":
            content = '{"summary":"mock structured output","disclaimer":"This is not financial advice."}'
        elif locale == "zh":
            content = "Mock LLM 生成的机构投研摘要。\n\nThis is not financial advice."
        else:
            content = "Mock LLM synthesis for institutional research.\n\nThis is not financial advice."
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(content.split()))
        status = "fallback_mock" if self.status == "fallback_mock" else "success"
        log_llm_call(
            db,
            user_id=user_id,
            provider=self.provider_name,
            model=self.model,
            task_type=task_type,
            locale=locale,
            prompt=prompt,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            status=status,
            error_message=self.last_error,
        )
        return LLMResponse(
            content=content,
            provider=self.provider_name,
            model=self.model,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            error_message=self.last_error,
        )
