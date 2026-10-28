"""Rate-limit keys must come from the trusted client address only.

X-Forwarded-For is client-controllable: honoring it lets a caller rotate the
header per request and get a fresh rate-limit bucket every time.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from apps.api.client_ip import client_ip
from apps.api.routers import captcha as captcha_module


def _request(headers: dict[str, str] | None = None, peer: tuple[str, int] | None = ("10.0.0.9", 5000)) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": peer,
    }
    return Request(scope)


def test_prefers_x_real_ip():
    request = _request({"X-Real-IP": " 203.0.113.7 ", "X-Forwarded-For": "198.51.100.1"})
    assert client_ip(request) == "203.0.113.7"


def test_ignores_x_forwarded_for_and_uses_socket_peer():
    request = _request({"X-Forwarded-For": "198.51.100.1, 10.0.0.1"})
    assert client_ip(request) == "10.0.0.9"


def test_unknown_without_peer():
    assert client_ip(_request(peer=None)) == "unknown"


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, seconds):
        return True


def test_rotating_x_forwarded_for_does_not_evade_captcha_rate_limit(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(captcha_module, "_is_production", lambda: True)
    monkeypatch.setattr(captcha_module, "_redis", lambda: redis)
    for index in range(captcha_module._RATE_LIMIT):
        captcha_module._rate_limit(_request({"X-Forwarded-For": f"198.51.100.{index}"}))
    with pytest.raises(HTTPException) as exc:
        captcha_module._rate_limit(_request({"X-Forwarded-For": "198.51.100.250"}))
    assert exc.value.status_code == 429
    assert len(redis.counts) == 1


@pytest.mark.parametrize(
    "path",
    ["apps/api/main.py", "apps/api/routers/auth.py", "apps/api/routers/captcha.py",
     "apps/api/routers/wallet_auth.py", "apps/api/routers/email_auth.py"],
)
def test_rate_limited_modules_never_read_x_forwarded_for(path):
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / path).read_text(encoding="utf-8").lower()
    assert 'get("x-forwarded-for")' not in source
    assert "client_ip(request)" in source
