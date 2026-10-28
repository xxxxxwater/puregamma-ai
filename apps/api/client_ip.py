"""Trusted client address for rate limits and abuse controls.

The edge proxy (Caddy) overwrites ``X-Real-IP`` with the address it decided
on (see ``Caddyfile``), so that header is the only one the API trusts.
``X-Forwarded-For`` is client-controllable — an attacker can rotate it per
request to get a fresh rate-limit bucket — and is deliberately never read.
Without ``X-Real-IP`` the socket peer is used.
"""

from __future__ import annotations

from starlette.requests import HTTPConnection


def client_ip(request: HTTPConnection) -> str:
    """Return the trusted client address: X-Real-IP, then the socket peer."""
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
