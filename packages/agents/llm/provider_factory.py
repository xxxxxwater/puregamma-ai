from __future__ import annotations

from apps.api.config import Settings, get_settings
from packages.agents.llm.base import LLMProvider
from packages.agents.llm.deepseek_provider import DeepSeekProvider
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.agents.llm.openai_provider import OpenAIProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    provider = (settings.llm_provider or "mock").lower()
    if provider == "deepseek":
        deepseek = DeepSeekProvider(settings)
        if not deepseek.configured:
            return MockLLMProvider(status="fallback_mock", last_error=deepseek.last_error)
        return deepseek
    if provider == "openai":
        openai = OpenAIProvider(settings)
        if not openai.configured:
            return MockLLMProvider(status="fallback_mock", last_error=openai.last_error)
        return openai
    return MockLLMProvider()


def llm_status(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    provider = get_llm_provider(settings)
    requested = (settings.llm_provider or "mock").lower()
    status = "healthy" if provider.provider_name == requested and provider.configured else "mock" if provider.provider_name == "mock" else "degraded"
    model = settings.deepseek_model if requested == "deepseek" else settings.openai_model if requested == "openai" else provider.model
    return {
        "provider": requested,
        "active_provider": provider.provider_name,
        "model": model or provider.model,
        "configured": provider.provider_name == requested and provider.configured,
        "status": status,
        "last_error": provider.last_error,
    }
