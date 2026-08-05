from __future__ import annotations

from apps.api.config import Settings
from packages.gateway.providers.openai_compatible import OfficialOpenAICompatibleProvider
from packages.gateway.registry import provider_registry


class MoonshotGatewayProvider(OfficialOpenAICompatibleProvider):
    provider_name = "moonshot"
    api_key_setting = "gateway_moonshot_api_key"
    base_url_setting = "gateway_moonshot_base_url"


@provider_registry.register("moonshot")
def create_provider(settings: Settings, metadata: dict) -> MoonshotGatewayProvider:
    return MoonshotGatewayProvider(settings, metadata)
