from __future__ import annotations

from apps.api.config import Settings, get_settings
from packages.agents.llm.base import LLMProvider
from packages.agents.llm.deepseek_provider import DeepSeekProvider
from packages.agents.llm.kimi_provider import KimiProvider
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
    if provider == "kimi":
        kimi = KimiProvider(settings)
        if not kimi.configured:
            return MockLLMProvider(status="fallback_mock", last_error=kimi.last_error)
        return kimi
    return MockLLMProvider()


def get_agent_llm_provider(selected_model: str | None = None, settings: Settings | None = None) -> LLMProvider:
    """Resolve an explicit user-selected Agent model without changing global defaults."""
    settings = settings or get_settings()
    if not selected_model or selected_model == "default":
        return get_llm_provider(settings)
    if selected_model != settings.openai_luna_model:
        raise ValueError("AGENT_MODEL_INVALID")
    if not settings.openai_luna_enabled or not settings.openai_api_key:
        raise RuntimeError("AGENT_MODEL_UNAVAILABLE")
    return OpenAIProvider(
        settings,
        model=settings.openai_luna_model,
        timeout_seconds=settings.openai_luna_timeout_seconds,
        reasoning_effort=settings.openai_luna_reasoning_effort,
    )


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
