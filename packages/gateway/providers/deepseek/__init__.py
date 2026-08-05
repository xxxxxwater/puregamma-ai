from __future__ import annotations

from apps.api.config import Settings
from packages.gateway.providers.openai_compatible import OfficialOpenAICompatibleProvider
from packages.gateway.registry import provider_registry


class DeepSeekGatewayProvider(OfficialOpenAICompatibleProvider):
    provider_name = "deepseek"
    api_key_setting = "gateway_deepseek_api_key"
    base_url_setting = "gateway_deepseek_base_url"


@provider_registry.register("deepseek")
def create_provider(settings: Settings, metadata: dict) -> DeepSeekGatewayProvider:
    return DeepSeekGatewayProvider(settings, metadata)
