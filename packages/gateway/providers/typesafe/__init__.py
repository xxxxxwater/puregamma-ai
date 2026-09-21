from __future__ import annotations

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

#: Jev ingests `state` once and evaluates every question against it. The
#: published budget is 64k total, with 32k for the state plus the longest
#: single question -- so the ceiling a caller can actually use is the smaller
#: one. Kept here as documentation for the catalog's capability block.
STATE_BUDGET_TOKENS = 32_768
REQUEST_BUDGET_TOKENS = 65_536


class TypeSafeGatewayProvider(GatewayProvider):
    """Adapter for TypeSafe's System One endpoint.

    This is deliberately *not* an ``OfficialOpenAICompatibleProvider``
    subclass. Jev does not speak the chat-completions shape at all: it takes a
    ``state`` plus a map of typed ``questions`` and returns structured
    ``answers`` with probabilities. Pretending otherwise -- by translating a
    chat request into a System One call, or by returning an answer as message
    content -- would bill customers for a conversation they did not have and
    hand them a shape their code cannot rely on.

    So the unimplemented capabilities raise :class:`GatewayCapabilityUnavailable`
    rather than degrading quietly, and the real operation is exposed as
    :meth:`systemOne`.
    """

    provider_name = "typesafe"
    api_key_setting = "gateway_typesafe_api_key"
    base_url_setting = "gateway_typesafe_base_url"

    def __init__(self, settings: Settings, metadata: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self.metadata = metadata or {}
        self.api_key = str(getattr(settings, self.api_key_setting, "") or "")
        self.base_url = str(
            self.metadata.get("base_url") or getattr(settings, self.base_url_setting, "")
        ).rstrip("/")
        self.timeout_seconds = int(self.metadata.get("timeout_seconds") or 60)

    # ---------------------------------------------------------------- plumbing
    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise GatewayProviderError(
                "GATEWAY_PROVIDER_UNCONFIGURED",
                f"{self.provider_name} is not configured",
                status_code=503,
                retryable=False,
            )
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _error(response: httpx.Response) -> GatewayProviderError:
        try:
            body = response.json()
            detail = body.get("detail") or body.get("error") or body
            message = str(detail.get("message") if isinstance(detail, dict) else detail)
        except Exception:
            message = response.text[:500] or "Provider request failed"
        # A bad key will not fix itself; a rate limit will.
        retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
        return GatewayProviderError(
            "GATEWAY_PROVIDER_HTTP_ERROR",
            message,
            status_code=502 if retryable else 400,
            retryable=retryable,
        )

    # ------------------------------------------------------- chat-shaped calls
    # Jev answers typed questions; it does not generate messages. Each of these
    # is a genuine capability gap, so it is reported as one instead of being
    # approximated. GATEWAY_CAPABILITY_UNAVAILABLE is 400 and not retryable.
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

    # ------------------------------------------------------------- the real op
    def systemOne(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        """Evaluate ``request["questions"]`` against ``request["state"]``.

        Only the fields the endpoint defines cross the provider boundary;
        routing and accounting fields stay on this side, matching the rule the
        OpenAI-compatible adapter already follows.

        Returns the upstream body unchanged, including the versioned ``model``
        id that answered -- an alias like ``jev-latest`` moves, so a stored
        answer has to carry the version that produced it.
        """
        questions = request.get("questions")
        if not isinstance(questions, dict) or not questions:
            raise GatewayProviderError(
                "GATEWAY_INVALID_REQUEST",
                "systemOne requires a non-empty questions object",
                status_code=400,
                retryable=False,
            )
        payload = {"state": request.get("state"), "model": model, "questions": questions}
        for optional in ("temperature", "top_p"):
            if optional in request:
                payload[optional] = request[optional]

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(self._url("systemone"), headers=self._headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise GatewayProviderError(
                "GATEWAY_PROVIDER_TIMEOUT", f"{self.provider_name} timed out", status_code=504
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayProviderError(
                "GATEWAY_PROVIDER_NETWORK_ERROR",
                f"{self.provider_name} network error",
                status_code=502,
            ) from exc
        if response.is_error:
            raise self._error(response)
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            raise GatewayProviderError(
                "GATEWAY_PROVIDER_INVALID_RESPONSE",
                f"{self.provider_name} returned no answers object",
                status_code=502,
                retryable=False,
            )
        return body

    # --------------------------------------------------------------- metering
    def tokenUsage(self, payload: dict[str, Any]) -> GatewayUsage:
        """Map a System One response onto the gateway's usage record.

        Output tokens are reported even though Jev does not bill for them: the
        gateway ledger should show what was consumed, and the catalog simply
        carries no ``output`` rate, so costing a System One request charges
        input only. Reporting 0 instead would hide real traffic.
        """
        usage = payload.get("usage") if isinstance(payload, dict) else None
        usage = usage if isinstance(usage, dict) else {}

        def _int(key: str) -> int:
            try:
                return max(0, int(usage.get(key) or 0))
            except (TypeError, ValueError):
                return 0

        return GatewayUsage(input_tokens=_int("input_tokens"), output_tokens=_int("output_tokens"))

    # ----------------------------------------------------------------- health
    def healthCheck(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(self._url("models"), headers=self._headers())
        except httpx.HTTPError as exc:
            raise GatewayProviderError(
                "GATEWAY_PROVIDER_NETWORK_ERROR",
                f"{self.provider_name} network error",
                status_code=502,
            ) from exc
        if response.is_error:
            raise self._error(response)
        return {"status": "ok", "provider": self.provider_name}

    # ---------------------------------------------------------------- catalog
    def getModels(self) -> list[ProviderModelMetadata]:
        return provider_models(self.provider_name)

    def getPricing(self) -> list[ProviderModelMetadata]:
        # TypeSafe publishes its price on the models page rather than through
        # an authenticated pricing API, so the reviewed catalog entry is the
        # source of truth. `pricing_path` stays supported for the day that
        # changes.
        return [item for item in self.getModels() if item.official_prices]


@provider_registry.register("typesafe")
def create_provider(settings: Settings, metadata: dict) -> TypeSafeGatewayProvider:
    return TypeSafeGatewayProvider(settings, metadata)
