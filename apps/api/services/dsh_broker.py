"""Logout linkage with the DSH session broker (multi-tenant DSH Web).

When a user logs out, FastAPI already rejects their Host tokens (the
session_version bump), but the broker would keep its short identity cache,
the user's open WebSocket tunnels and the running Host until they expire. With
``DSH_BROKER_REVOKE_URL`` set, logout tells the broker to drop all three at
once. Off by default (and whenever DSH_MULTI_TENANT_ENABLED is off); a
failure is logged and never affects the logout itself. The broker also
re-checks open tunnels on its own (PUREGAMMA_DSH_SOCKET_REVALIDATE_MS), so
this is a speed-up, not the only control.
"""
from __future__ import annotations

import logging

from apps.api.config import get_settings

logger = logging.getLogger("puregamma.dsh_broker")


def broker_revoke_enabled() -> bool:
    settings = get_settings()
    return bool(
        settings.dsh_multi_tenant_enabled
        and settings.dsh_broker_revoke_url
        and len(settings.dsh_broker_secret) >= 32
    )


def notify_broker_logout(user_id: str) -> bool:
    """POST ``{"user_id": ...}`` to the broker's revoke endpoint. Returns True on 204."""
    if not broker_revoke_enabled():
        return False
    settings = get_settings()
    import httpx

    try:
        response = httpx.post(
            settings.dsh_broker_revoke_url,
            json={"user_id": user_id},
            headers={"X-PureGamma-Broker-Secret": settings.dsh_broker_secret},
            timeout=2.0,
            follow_redirects=False,
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:  # never let the notification break logout
        logger.warning("dsh_broker_revoke_failed: %s", type(exc).__name__)
        return False
    if response.status_code != 204:
        logger.warning("dsh_broker_revoke_rejected: HTTP %s", response.status_code)
        return False
    return True
