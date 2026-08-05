from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Iterator

from sqlalchemy.orm import Session

from packages.agents.llm.cost_tracker import log_llm_call
from packages.agents.llm.schemas import ChatMessage, LLMResponse, LLMStreamChunk


class LLMProvider(ABC):
    provider_name: str
    model: str
    configured: bool = True
    last_error: str | None = None

    @abstractmethod
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
        raise NotImplementedError

    def complete(self, prompt: str, *, task_type: str, locale: str = "en", user_id: str | None = None, db: Session | None = None) -> str:
        return self.chat([ChatMessage(role="user", content=prompt)], task_type=task_type, locale=locale, user_id=user_id, db=db).content

    def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        task_type: str,
        locale: str = "en",
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Iterator[LLMStreamChunk]:
        response = self.chat(messages, task_type=task_type, locale=locale, user_id=user_id, db=db)
        yield LLMStreamChunk(delta=response.content, provider=response.provider, model=response.model)
        yield LLMStreamChunk(done=True, provider=response.provider, model=response.model, prompt_tokens=response.prompt_tokens, completion_tokens=response.completion_tokens)

    def structured_json(
        self,
        prompt: str,
        *,
        task_type: str,
        locale: str = "en",
        user_id: str | None = None,
        db: Session | None = None,
    ) -> dict[str, Any]:
        response = self.chat(
            [ChatMessage(role="user", content=prompt)],
            task_type=task_type,
            locale=locale,
            user_id=user_id,
            db=db,
            response_format="json_object",
        )
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            repaired = self.chat(
                [ChatMessage(role="user", content=f"Repair this into valid JSON only:\n{response.content}")],
                task_type=f"{task_type}_json_repair",
                locale=locale,
                user_id=user_id,
                db=db,
                response_format="json_object",
            )
            try:
                return json.loads(repaired.content)
            except json.JSONDecodeError as exc:
                log_llm_call(
                    db,
                    user_id=user_id,
                    provider=self.provider_name,
                    model=self.model,
                    task_type=task_type,
                    locale=locale,
                    prompt=prompt,
                    prompt_tokens=max(1, len(prompt.split())),
                    completion_tokens=0,
                    status="failed",
                    error_message=f"Invalid JSON after repair: {exc}",
                )
                raise
