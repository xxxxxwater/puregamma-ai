from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from apps.api.config import Settings

if TYPE_CHECKING:
    from packages.gateway.contracts import GatewayProvider


ProviderFactory = Callable[[Settings, dict], "GatewayProvider"]


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str) -> Callable[[ProviderFactory], ProviderFactory]:
        normalized = name.strip().lower()

        def decorator(factory: ProviderFactory) -> ProviderFactory:
            if normalized in self._factories:
                raise RuntimeError(f"Gateway provider already registered: {normalized}")
            self._factories[normalized] = factory
            return factory

        return decorator

    def create(self, name: str, settings: Settings, metadata: dict | None = None) -> "GatewayProvider":
        ensure_builtin_providers()
        try:
            return self._factories[name.strip().lower()](settings, metadata or {})
        except KeyError as exc:
            raise ValueError(f"GATEWAY_PROVIDER_NOT_REGISTERED:{name}") from exc

    def names(self) -> tuple[str, ...]:
        ensure_builtin_providers()
        return tuple(sorted(self._factories))


provider_registry = ProviderRegistry()
_loaded = False


def ensure_builtin_providers() -> None:
    global _loaded
    if _loaded:
        return
    # Imports register plugins. Adding a provider is additive and never
    # requires a Router branch.
    import packages.gateway.providers.deepseek  # noqa: F401
    import packages.gateway.providers.glm  # noqa: F401
    import packages.gateway.providers.moonshot  # noqa: F401

    _loaded = True
