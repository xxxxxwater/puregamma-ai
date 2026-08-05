from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator


class GatewayProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 502, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class GatewayCapabilityUnavailable(GatewayProviderError):
    def __init__(self, capability: str) -> None:
        super().__init__("GATEWAY_CAPABILITY_UNAVAILABLE", f"Provider does not support {capability}", status_code=400, retryable=False)


@dataclass(frozen=True)
class GatewayUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    reasoning_tokens: int = 0
    long_context_tokens: int = 0
    image_units: int = 0
    audio_units: int = 0
    search_units: int = 0
    upload_units: int = 0
    download_units: int = 0
    batch_units: int = 0


@dataclass(frozen=True)
class GatewayChatResult:
    content: str | None
    finish_reason: str | None
    usage: GatewayUsage
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    function_call: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayStreamEvent:
    delta: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: GatewayUsage | None = None
    done: bool = False


@dataclass(frozen=True)
class ProviderModelMetadata:
    public_id: str
    provider_model_id: str
    display_name: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    official_prices: dict[str, Any] = field(default_factory=dict)
    source_reference: str | None = None


class GatewayProvider(ABC):
    """Plugin boundary: Router code can only call this interface."""

    provider_name: str

    @abstractmethod
    def chat(self, model: str, request: dict[str, Any]) -> GatewayChatResult:
        raise NotImplementedError

    @abstractmethod
    def stream(self, model: str, request: dict[str, Any]) -> Iterator[GatewayStreamEvent]:
        raise NotImplementedError

    @abstractmethod
    def embedding(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def image(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def audio(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def rerank(self, model: str, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def healthCheck(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def tokenUsage(self, payload: dict[str, Any]) -> GatewayUsage:
        raise NotImplementedError

    @abstractmethod
    def getPricing(self) -> list[ProviderModelMetadata]:
        raise NotImplementedError

    @abstractmethod
    def getModels(self) -> list[ProviderModelMetadata]:
        raise NotImplementedError

    # Python-friendly aliases keep service code readable while preserving the
    # explicit plugin contract used by integrations and provider authors.
    def health_check(self) -> dict[str, Any]:
        return self.healthCheck()

    def token_usage(self, payload: dict[str, Any]) -> GatewayUsage:
        return self.tokenUsage(payload)

    def get_pricing(self) -> list[ProviderModelMetadata]:
        return self.getPricing()

    def get_models(self) -> list[ProviderModelMetadata]:
        return self.getModels()
