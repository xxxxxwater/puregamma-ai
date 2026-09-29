from __future__ import annotations

from packages.data.provider import ProviderError


class MacroProvider:
    """Legacy macro facade. Fixed narratives are forbidden in production."""

    def summary(self) -> dict:
        raise ProviderError(
            "provider_unavailable",
            "Legacy macro summary is disabled; use timestamped reviewed macro evidence",
        )
