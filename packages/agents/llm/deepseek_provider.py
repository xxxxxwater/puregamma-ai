from __future__ import annotations

import time
from typing import Iterator

from sqlalchemy.orm import Session

from apps.api.config import Settings
from packages.agents.llm.base import LLMProvider
from packages.agents.llm.cost_tracker import log_llm_call, redact_text
from packages.agents.llm.schemas import ChatMessage, LLMResponse, LLMStreamChunk


class DeepSeekProvider(LLMProvider):
    """Direct DeepSeek provider for platform-owned (non-gateway) model calls.

    The model actually sent upstream is ``settings.deepseek_effective_model``,
    which resolves retired names such as ``deepseek-v4-flash`` to the model that
    really serves them (``deepseek-flash`` / DeepSeek V4.1 Flash). Logs and
    responses report the resolved id, so usage records never claim a model that
    did not run.
    """

    provider_name = "deepseek"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.deepseek_effective_model
        self.base_url = settings.deepseek_base_url or "https://api.deepseek.com"
        self.configured = bool(settings.deepseek_api_key)
        self.last_error = None if self.configured else "DEEPSEEK_API_KEY is not configured"

    # ------------------------------------------------------------------
    # Request shaping
    # ------------------------------------------------------------------
    def _system_prompt(self, locale: str) -> str:
        return (
            "使用简体中文，保持专业、克制、机构投研风格。"
            if locale == "zh"
            else "Use institutional English. Keep the tone concise, disciplined, and research-oriented."
        )

    def _thinking_kwargs(self) -> dict:
        """DeepSeek thinking-mode controls.

        ``thinking`` is an OpenAI-compatible extension parameter and must travel
        in ``extra_body`` through the OpenAI SDK. ``reasoning_effort`` only
        means something while thinking is on; DeepSeek maps ``low``/``high``/
        ``max`` and ignores anything else.
        """
        if not self.settings.deepseek_thinking_enabled:
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        kwargs: dict = {
            "extra_body": {"thinking": {"type": "enabled"}},
            "reasoning_effort": self.settings.deepseek_effective_reasoning_effort,
        }
        return kwargs

    def _client(self, *, timeout: float):
        from openai import OpenAI

        return OpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    @staticmethod
    def _reasoning_tokens(usage: object) -> int:
        details = getattr(usage, "completion_tokens_details", None)
        value = getattr(details, "reasoning_tokens", None) if details is not None else None
        return int(value or 0)

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
                client = self._client(timeout=self.settings.deepseek_timeout_seconds)
                kwargs: dict = {}
                if response_format == "json_object":
                    kwargs["response_format"] = {"type": "json_object"}
                # DeepSeek ignores temperature while thinking is enabled, so it
                # is only sent for the non-thinking path.
                if not self.settings.deepseek_thinking_enabled:
                    kwargs["temperature"] = self.settings.agent_temperature
                kwargs.update(self._thinking_kwargs())
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": self._system_prompt(locale)}, *[{"role": message.role, "content": message.content} for message in messages]],
                    **kwargs,
                )
                content = response.choices[0].message.content or ""
                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or max(1, len(prompt.split())))
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or max(1, len(content.split())))
                reasoning_tokens = self._reasoning_tokens(usage) if usage is not None else 0
                log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="success")
                return LLMResponse(content=content, provider=self.provider_name, model=self.model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens, reasoning_tokens=reasoning_tokens)
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
        last_error: Exception | None = None
        yielded = False
        for attempt in range(3):
            if yielded:
                break
            try:
                client = self._client(timeout=self.settings.agent_request_timeout_ms / 1000)
                kwargs: dict = {"stream": True}
                if not self.settings.deepseek_thinking_enabled:
                    # A reasoning budget would be spent before any visible
                    # token, so this path keeps the explicit answer cap.
                    kwargs["temperature"] = self.settings.agent_temperature
                    kwargs["max_tokens"] = self.settings.agent_max_output_tokens
                kwargs.update(self._thinking_kwargs())
                stream = client.chat.completions.create(model=self.model, messages=[{"role": "system", "content": self._system_prompt(locale)}, *[{"role": message.role, "content": message.content} for message in messages]], **kwargs)
                for chunk in stream:
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or prompt_tokens)
                        completion_tokens = int(getattr(usage, "completion_tokens", 0) or completion_tokens)
                    choices = getattr(chunk, "choices", []) or []
                    delta = getattr(choices[0].delta, "content", None) if choices else None
                    if delta:
                        yielded = True
                        completion_tokens += max(1, len(delta.split()))
                        yield LLMStreamChunk(delta=delta, provider=self.provider_name, model=self.model)
                log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="success")
                yield LLMStreamChunk(done=True, provider=self.provider_name, model=self.model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
                return
            except Exception as exc:
                last_error = exc
                self.last_error = redact_text(str(exc))
                if attempt < 2:
                    time.sleep(0.2 * (2 ** attempt))
        log_llm_call(db, user_id=user_id, provider=self.provider_name, model=self.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, status="failed", error_message=self.last_error)
        raise RuntimeError(self.last_error or str(last_error))
