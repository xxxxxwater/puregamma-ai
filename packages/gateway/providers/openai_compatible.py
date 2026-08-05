from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

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


class OfficialOpenAICompatibleProvider(GatewayProvider):
    """A narrow adapter for providers that expose their official OpenAI API."""

    provider_name = "official_openai_compatible"
    api_key_setting = ""
    base_url_setting = ""

    def __init__(self, settings: Settings, metadata: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self.metadata = metadata or {}
        self.api_key = str(getattr(settings, self.api_key_setting, "") or "")
        self.base_url = str(self.metadata.get("base_url") or getattr(settings, self.base_url_setting, "")).rstrip("/")
        self.timeout_seconds = int(self.metadata.get("timeout_seconds") or 90)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise GatewayProviderError("GATEWAY_PROVIDER_UNCONFIGURED", f"{self.provider_name} is not configured", status_code=503, retryable=False)
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _error(response: httpx.Response) -> GatewayProviderError:
        try:
            body = response.json()
            detail = body.get("error", body) if isinstance(body, dict) else body
            message = str(detail.get("message") if isinstance(detail, dict) else detail)
        except Exception:
            message = response.text[:500] or "Provider request failed"
        retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
        return GatewayProviderError("GATEWAY_PROVIDER_HTTP_ERROR", message, status_code=502 if retryable else 400, retryable=retryable)

    def _request_payload(self, model: str, request: dict[str, Any], *, stream: bool) -> dict[str, Any]:
        # Only pass OpenAI-compatible user parameters. Routing, API-key, and
        # accounting fields cannot cross the provider boundary.
        allowed = {
            "messages", "temperature", "top_p", "max_tokens", "max_completion_tokens",
            "response_format", "tools", "tool_choice", "functions", "function_call",
            "stop", "n", "presence_penalty", "frequency_penalty", "logit_bias",
            "seed", "user", "stream_options",
        }
        payload = {key: value for key, value in request.items() if key in allowed}
        payload["model"] = model
        payload["stream"] = stream
        if stream:
            options = dict(payload.get("stream_options") or {})
            options["include_usage"] = True
            payload["stream_options"] = options
        return payload

    def chat(self, model: str, request: dict[str, Any]) -> GatewayChatResult:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(self._url("chat/completions"), headers=self._headers(), json=self._request_payload(model, request, stream=False))
        except httpx.TimeoutException as exc:
            raise GatewayProviderError("GATEWAY_PROVIDER_TIMEOUT", f"{self.provider_name} timed out", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise GatewayProviderError("GATEWAY_PROVIDER_NETWORK_ERROR", f"{self.provider_name} network error", status_code=502) from exc
        if response.is_error:
            raise self._error(response)
        payload = response.json()
        choices = payload.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        return GatewayChatResult(
            content=message.get("content"),
            finish_reason=choice.get("finish_reason"),
            usage=self.tokenUsage(payload),
            tool_calls=list(message.get("tool_calls") or []),
            function_call=dict(message["function_call"]) if isinstance(message.get("function_call"), dict) else None,
            raw=payload,
        )

    def stream(self, model: str, request: dict[str, Any]) -> Iterator[GatewayStreamEvent]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", self._url("chat/completions"), headers=self._headers(), json=self._request_payload(model, request, stream=True)) as response:
                    if response.is_error:
                        raise self._error(response)
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield GatewayStreamEvent(done=True)
                            return
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = payload.get("choices") or []
                        choice = choices[0] if choices else {}
                        usage = self.tokenUsage(payload) if payload.get("usage") else None
                        yield GatewayStreamEvent(
                            delta=dict(choice.get("delta") or {}),
                            finish_reason=choice.get("finish_reason"),
                            usage=usage,
                        )
        except GatewayProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise GatewayProviderError("GATEWAY_PROVIDER_TIMEOUT", f"{self.provider_name} timed out", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise GatewayProviderError("GATEWAY_PROVIDER_NETWORK_ERROR", f"{self.provider_name} network error", status_code=502) from exc

    def _capability_request(self, capability: str, model: str, request: dict[str, Any]) -> dict[str, Any]:
        endpoint = (self.metadata.get("endpoints") or {}).get(capability)
        if not endpoint:
            raise GatewayCapabilityUnavailable(capability)
        payload = dict(request)
        payload["model"] = model
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(self._url(str(endpoint)), headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise GatewayProviderError("GATEWAY_PROVIDER_NETWORK_ERROR", f"{self.provider_name} network error") from exc
        if response.is_error:
            raise self._error(response)
        return response.json()

    def embedding(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        return self._capability_request("embedding", model, request)

    def image(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        return self._capability_request("image", model, request)

    def audio(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        return self._capability_request("audio", model, request)

    def rerank(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        return self._capability_request("rerank", model, request)

    def healthCheck(self) -> dict[str, Any]:
        if not self.api_key or not self.base_url:
            return {"healthy": False, "status": "unconfigured", "error": "Provider credentials are not configured"}
        path = str(self.metadata.get("health_path") or "models")
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(self._url(path), headers=self._headers())
            # Authentication and endpoint errors must remove a provider from
            # routing just as decisively as a 5xx.  Treating 401/404 as
            # healthy would cause customer requests to be sent to a known-bad
            # route until the next real request failed.
            healthy = 200 <= response.status_code < 300
            return {
                "healthy": healthy,
                "status": "healthy" if healthy else "unhealthy",
                "http_status": response.status_code,
                **({"error": f"HTTP {response.status_code}"} if not healthy else {}),
            }
        except httpx.HTTPError as exc:
            return {"healthy": False, "status": "unhealthy", "error": type(exc).__name__}

    def tokenUsage(self, payload: dict[str, Any]) -> GatewayUsage:
        usage = payload.get("usage") or payload
        if not isinstance(usage, dict):
            return GatewayUsage()
        completion_details = usage.get("completion_tokens_details") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        return GatewayUsage(
            input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            cache_tokens=int(prompt_details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or usage.get("cache_tokens") or 0),
            reasoning_tokens=int(completion_details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0),
            long_context_tokens=int(usage.get("long_context_tokens") or 0),
            image_units=int(usage.get("image_units") or 0),
            audio_units=int(usage.get("audio_units") or 0),
            search_units=int(usage.get("search_units") or 0),
            upload_units=int(usage.get("upload_units") or 0),
            download_units=int(usage.get("download_units") or 0),
            batch_units=int(usage.get("batch_units") or 0),
        )

    def getModels(self) -> list[ProviderModelMetadata]:
        return provider_models(self.provider_name)

    def getPricing(self) -> list[ProviderModelMetadata]:
        configured = self.getModels()
        pricing_path = self.metadata.get("pricing_path")
        if not pricing_path:
            return [item for item in configured if item.official_prices]

        # A provider may expose official pricing as an authenticated JSON API.
        # Field names stay in Provider metadata so Router/Pricing code never
        # learns provider-specific response schemas. A YAML catalog remains the
        # fallback for providers that publish a file rather than an endpoint.
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(self._url(str(pricing_path)), headers=self._headers())
        except httpx.HTTPError as exc:
            raise GatewayProviderError("GATEWAY_PRICING_SYNC_NETWORK_ERROR", f"{self.provider_name} pricing sync failed", status_code=502) from exc
        if response.is_error:
            raise self._error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise GatewayProviderError("GATEWAY_PRICING_SYNC_INVALID_RESPONSE", f"{self.provider_name} pricing response is invalid", status_code=502, retryable=False) from exc
        collection_key = str(self.metadata.get("pricing_response_key") or "data")
        rows = payload.get(collection_key, []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise GatewayProviderError("GATEWAY_PRICING_SYNC_INVALID_RESPONSE", f"{self.provider_name} pricing response is invalid", status_code=502, retryable=False)
        model_field = str(self.metadata.get("pricing_model_field") or "id")
        price_field = str(self.metadata.get("pricing_field") or "pricing")
        values = {
            str(row.get(model_field)): row.get(price_field)
            for row in rows
            if isinstance(row, dict) and row.get(model_field) and isinstance(row.get(price_field), dict)
        }
        reference = str(self.metadata.get("pricing_source_reference") or self._url(str(pricing_path)))
        return [
            ProviderModelMetadata(
                public_id=item.public_id,
                provider_model_id=item.provider_model_id,
                display_name=item.display_name,
                capabilities=item.capabilities,
                metadata=item.metadata,
                official_prices=dict(values.get(item.provider_model_id) or item.official_prices),
                source_reference=reference if values.get(item.provider_model_id) else item.source_reference,
            )
            for item in configured
            if values.get(item.provider_model_id) or item.official_prices
        ]
