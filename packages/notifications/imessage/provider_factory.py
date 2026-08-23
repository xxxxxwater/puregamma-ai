from __future__ import annotations

"""Shared iMessage provider selection.

Both the notification dispatcher and the verification service must resolve
the configured iMessage provider the same way. Keeping that decision here
(instead of importing NotificationDispatcher from the verification service,
which would create an import cycle through normalize_e164) gives a single
equivalent factory for every caller.
"""

from apps.api.config import Settings, get_settings
from packages.notifications.imessage.base import IMessageProvider
from packages.notifications.imessage.macos_relay_client import MacOSIMessageRelayClient
from packages.notifications.imessage.mock_provider import MockIMessageProvider
from packages.notifications.imessage.photon_provider import PhotonIMessageProvider


def get_imessage_provider(settings: Settings | None = None) -> IMessageProvider:
    settings = settings or get_settings()
    if settings.imessage_provider == "macos_relay":
        return MacOSIMessageRelayClient()
    if settings.imessage_provider == "photon":
        return PhotonIMessageProvider()
    if settings.app_environment.lower() != "production" and settings.imessage_provider == "mock":
        return MockIMessageProvider()
    raise RuntimeError("IMESSAGE_PROVIDER_UNAVAILABLE")
