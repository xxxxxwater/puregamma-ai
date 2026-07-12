from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from apps.api.config import Settings
from packages.agents.llm.base import LLMProvider
from packages.agents.llm.cost_tracker import log_llm_call, redact_text
from packages.agents.llm.schemas import ChatMessage, LLMResponse, LLMStreamChunk


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.openai_model or settings.llm_model or "gpt-4o-mini"
        self.configured = bool(settings.openai_api_key)
        self.last_error = None if self.configured else "OPENAI_API_KEY is not configured"

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
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None, timeout=60)
            kwargs = {}
            if response_format == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": message.role, "content": message.content} for message in messages],
                **kwargs,
            )
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or max(1, len(prompt.split())))
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or max(1, len(content.split())))
            log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="success")
            return LLMResponse(content=content, provider=self.provider_name, model=self.model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens)
        except Exception as exc:
            self.last_error = redact_text(str(exc))
            log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=max(1, len(prompt.split())), completion_tokens=0, status="failed", error_message=self.last_error)
            raise

    def stream_chat(self, messages: list[ChatMessage], *, task_type: str, locale: str = "en", user_id: str | None = None, db: Session | None = None) -> Iterator[LLMStreamChunk]:
        prompt = "\n".join(message.content for message in messages)
        completion_tokens = 0
        prompt_tokens = max(1, len(prompt.split()))
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None, timeout=self.settings.agent_request_timeout_ms / 1000)
            stream = client.chat.completions.create(
                model=self.model,
                messages=[{"role": message.role, "content": message.content} for message in messages],
                temperature=self.settings.agent_temperature,
                max_tokens=self.settings.agent_max_output_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage:
                    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or prompt_tokens)
                    completion_tokens = int(getattr(usage, "completion_tokens", 0) or completion_tokens)
                choices = getattr(chunk, "choices", []) or []
                delta = getattr(choices[0].delta, "content", None) if choices else None
                if delta:
                    completion_tokens += max(1, len(delta.split()))
                    yield LLMStreamChunk(delta=delta, provider=self.provider_name, model=self.model)
            log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="success")
            yield LLMStreamChunk(done=True, provider=self.provider_name, model=self.model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        except Exception as exc:
            self.last_error = redact_text(str(exc))
            log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="failed", error_message=self.last_error)
            raise
