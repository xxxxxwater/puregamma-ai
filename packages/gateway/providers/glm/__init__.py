from __future__ import annotations

from apps.api.config import Settings
from packages.gateway.providers.openai_compatible import OfficialOpenAICompatibleProvider
from packages.gateway.registry import provider_registry


class GLMGatewayProvider(OfficialOpenAICompatibleProvider):
    provider_name = "glm"
    api_key_setting = "gateway_glm_api_key"
    base_url_setting = "gateway_glm_base_url"


@provider_registry.register("glm")
def create_provider(settings: Settings, metadata: dict) -> GLMGatewayProvider:
    return GLMGatewayProvider(settings, metadata)
