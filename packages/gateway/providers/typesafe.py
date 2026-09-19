"""Official TypeSafe System One adapter. Jev is not a chat-completions model.

Credentials are server-side only. No user state, provider response body, or API
key is put into error strings or operational logs.
"""
from __future__ import annotations

import os
from typing import Any, Iterator

import httpx

from apps.api.config import Settings
from packages.gateway.catalog import provider_models
from packages.gateway.contracts import (
    GatewayCapabilityUnavailable,
    GatewayChatResult,
    GatewayProvider,
    GatewayProviderError,
    GatewayStreamEvent,
    GatewayUsage,
    ProviderModelMetadata,
)
from packages.gateway.registry import provider_registry


@provider_registry.register("typesafe")
def build_provider(settings: Settings, metadata: dict) -> "TypeSafeJevProvider":
    return TypeSafeJevProvider(settings, metadata)


class TypeSafeJevProvider(GatewayProvider):
    provider_name = "typesafe"
    # An operator must provision this independently from other model keys.
    # Never accept a caller-supplied URL or a catalog override of the host.
    base_url = "https://api.typesafe.ai"

    def __init__(self, settings: Settings, metadata: dict[str, Any] | None = None) -> None:
        self.api_key = os.environ.get("GATEWAY_TYPESAFE_API_KEY", "").strip()
        self.timeout_seconds = 20

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise GatewayProviderError("GATEWAY_PROVIDER_UNCONFIGURED", "TypeSafe provider is not configured", status_code=503, retryable=False)
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Accept": "application/json"}

    def evaluate(self, model: str, *, state: str | dict | list, questions: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], GatewayUsage]:
        """One upstream POST, no automatic retry of a potentially billed request."""
        if model != "jev-1.13.0":
            raise GatewayProviderError("GATEWAY_JEV_MODEL_UNSUPPORTED", "Unsupported Jev model version", status_code=400, retryable=False)
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = client.post(
                    f"{self.base_url}/v1/systemone",
                    headers=self._headers(),
                    json={"model": model, "state": state, "questions": questions},
                )
        except httpx.TimeoutException as exc:
            raise GatewayProviderError("GATEWAY_JEV_TIMEOUT", "TypeSafe request timed out; delivery status is unknown", status_code=504, retryable=False) from exc
        except httpx.HTTPError as exc:
            raise GatewayProviderError("GATEWAY_JEV_NETWORK_ERROR", "TypeSafe request failed; delivery status is unknown", status_code=502, retryable=False) from exc
        if response.status_code >= 400:
            status = 429 if response.status_code == 429 else 503 if response.status_code in {401, 403, 529} else 502
            raise GatewayProviderError("GATEWAY_JEV_UPSTREAM_ERROR", f"TypeSafe returned HTTP {response.status_code}", status_code=status, retryable=False)
        try:
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("model"), str):
                raise ValueError("Missing model")
            answers = body.get("answers")
            if not isinstance(answers, dict) or set(answers) != set(questions):
                raise ValueError("Missing or extra answers")
            for question_id, question in questions.items():
                answer = answers[question_id]
                if not isinstance(answer, dict) or answer.get("type") != question["type"]:
                    raise ValueError("Invalid answer type")
                if question["type"] == "noul":
                    score = answer.get("noul")
                    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
                        raise ValueError("Invalid noul")
                elif question["type"] == "choice":
                    if answer.get("choice") not in question["criteria"] or not isinstance(answer.get("probabilities"), dict):
                        raise ValueError("Invalid choice")
                elif question["type"] == "score":
                    if not isinstance(answer.get("score"), (int, float)) or not isinstance(answer.get("probabilities"), dict):
                        raise ValueError("Invalid score")
            usage = body.get("usage")
            if not isinstance(usage, dict):
                raise ValueError("Missing usage")
            input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
            if type(input_tokens) is not int or input_tokens < 0 or type(output_tokens) is not int or output_tokens < 0:
                raise ValueError("Invalid usage")
            return {"model": body["model"], "answers": answers, "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}, GatewayUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        except (TypeError, KeyError, ValueError) as exc:
            raise GatewayProviderError("GATEWAY_JEV_INVALID_RESPONSE", "TypeSafe returned an invalid response", status_code=502, retryable=False) from exc

    def chat(self, model: str, request: dict[str, Any]) -> GatewayChatResult:
        raise GatewayCapabilityUnavailable("chat")

    def stream(self, model: str, request: dict[str, Any]) -> Iterator[GatewayStreamEvent]:
        raise GatewayCapabilityUnavailable("stream")

    def embedding(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise GatewayCapabilityUnavailable("embedding")

    def image(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise GatewayCapabilityUnavailable("image")

    def audio(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise GatewayCapabilityUnavailable("audio")

    def rerank(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise GatewayCapabilityUnavailable("rerank")

    def healthCheck(self) -> dict[str, Any]:
        if not self.api_key:
            return {"healthy": False, "status": "unconfigured", "error": "Provider credentials are not configured"}
        try:
            with httpx.Client(timeout=5, follow_redirects=False) as client:
                response = client.get(f"{self.base_url}/v1/models", headers=self._headers())
            healthy = response.status_code == 200
            return {"healthy": healthy, "status": "healthy" if healthy else "unhealthy", "http_status": response.status_code, **({"error": f"HTTP {response.status_code}"} if not healthy else {})}
        except httpx.HTTPError as exc:
            return {"healthy": False, "status": "unhealthy", "error": type(exc).__name__}

    def tokenUsage(self, payload: dict[str, Any]) -> GatewayUsage:
        usage = payload.get("usage")
        if not isinstance(usage, dict) or type(usage.get("input_tokens")) is not int or type(usage.get("output_tokens")) is not int:
            raise GatewayProviderError("GATEWAY_JEV_INVALID_USAGE", "TypeSafe usage is missing", status_code=502, retryable=False)
        if usage["input_tokens"] < 0 or usage["output_tokens"] < 0:
            raise GatewayProviderError("GATEWAY_JEV_INVALID_USAGE", "TypeSafe usage is invalid", status_code=502, retryable=False)
        return GatewayUsage(input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"])

    def getModels(self) -> list[ProviderModelMetadata]:
        return provider_models(self.provider_name)

    def getPricing(self) -> list[ProviderModelMetadata]:
        return [item for item in self.getModels() if item.official_prices]
