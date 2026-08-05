from __future__ import annotations

import time
from typing import Iterator

from sqlalchemy.orm import Session

from apps.api.config import Settings
from packages.agents.llm.base import LLMProvider
from packages.agents.llm.cost_tracker import log_llm_call, redact_text
from packages.agents.llm.schemas import ChatMessage, LLMResponse, LLMStreamChunk


class KimiProvider(LLMProvider):
    provider_name = "kimi"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.kimi_model or "kimi-k3"
        self.base_url = settings.kimi_base_url or "https://api.moonshot.ai/v1"
        self.enabled = bool(settings.kimi_enabled)
        self.configured = self.enabled and bool(settings.kimi_api_key)
        if not self.enabled:
            self.last_error = "KIMI_ENABLED is false"
        elif not settings.kimi_api_key:
            self.last_error = "KIMI_API_KEY is not configured"
        else:
            self.last_error = None

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
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.settings.kimi_api_key, base_url=self.base_url, timeout=self.settings.kimi_timeout_seconds)
                system = "使用简体中文，保持专业、克制、机构投研风格。" if locale == "zh" else "Use institutional English. Keep the tone concise, disciplined, and research-oriented."
                kwargs = {}
                if response_format == "json_object":
                    kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, *[{"role": message.role, "content": message.content} for message in messages]],
                    **kwargs,
                )
                content = response.choices[0].message.content or ""
                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or max(1, len(prompt.split())))
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or max(1, len(content.split())))
                log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="success")
                return LLMResponse(content=content, provider=self.provider_name, model=self.model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens)
            except Exception as exc:
                last_error = exc
                self.last_error = redact_text(str(exc))
                if attempt < 2:
                    time.sleep(0.2 * (2 ** attempt))
        log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=max(1, len(prompt.split())), completion_tokens=0, status="failed", error_message=self.last_error)
        raise RuntimeError(self.last_error or str(last_error))

    def stream_chat(self, messages: list[ChatMessage], *, task_type: str, locale: str = "en", user_id: str | None = None, db: Session | None = None) -> Iterator[LLMStreamChunk]:
        prompt = "\n".join(message.content for message in messages)
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = 0
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.settings.kimi_api_key, base_url=self.base_url, timeout=self.settings.agent_request_timeout_ms / 1000)
            system = "使用简体中文，保持专业、克制、机构投研风格。" if locale == "zh" else "Use institutional English. Keep the tone concise, disciplined, and research-oriented."
            stream = client.chat.completions.create(model=self.model, messages=[{"role": "system", "content": system}, *[{"role": message.role, "content": message.content} for message in messages]], temperature=self.settings.agent_temperature, max_tokens=self.settings.agent_max_output_tokens, stream=True)
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
