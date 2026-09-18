from __future__ import annotations

import pytest

from apps.api.config import get_settings
from apps.api.routers.mobile_auth import WEB_SESSION_TTL_SECONDS
from packages.database.models import utcnow

RELAY = {"x-pocket-rpc-token": "relay-secret"}


@pytest.fixture()
def relay_login():
    """Configure the relay-only login handoff. Settings is a frozen singleton,
    so the values are written straight onto the cached instance and restored."""
    settings = get_settings()
    names = ("pocket_remote_email", "api_public_url", "pocket_rpc_secret")
    original = {name: getattr(settings, name) for name in names}

    def _configure(**values):
        for name, value in values.items():
            object.__setattr__(settings, name, value)

    yield _configure
    for name, value in original.items():
        object.__setattr__(settings, name, value)


def test_handoff_requires_the_relay_secret(api_client, relay_login):
    relay_login(
        pocket_remote_email="ops@puregamma.ai",
        api_public_url="https://api.puregamma.ai",
        pocket_rpc_secret="relay-secret",
    )
    assert api_client.post("/api/mobile-access/session-handoff").status_code == 403
    assert api_client.post("/api/mobile-access/session-handoff", headers={"x-pocket-rpc-token": "nope"}).status_code == 403


def test_handoff_stays_closed_until_an_account_is_configured(api_client, relay_login):
    relay_login(pocket_remote_email="", api_public_url="https://api.puregamma.ai", pocket_rpc_secret="relay-secret")
    response = api_client.post("/api/mobile-access/session-handoff", headers=RELAY)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REMOTE_LOGIN_NOT_CONFIGURED"

    relay_login(pocket_remote_email="ghost@puregamma.ai")
    missing = api_client.post("/api/mobile-access/session-handoff", headers=RELAY)
    assert missing.status_code == 503
    assert missing.json()["detail"]["code"] == "REMOTE_LOGIN_ACCOUNT_MISSING"


def test_handoff_mints_a_single_use_login_for_the_remote_account(api_client, db, user_factory, relay_login):
    user = user_factory("ops@puregamma.ai", role="admin")
    user.email_verified_at = utcnow()
    db.commit()
    relay_login(
        pocket_remote_email="ops@puregamma.ai",
        api_public_url="https://api.puregamma.ai",
        pocket_rpc_secret="relay-secret",
    )

    response = api_client.post(
        "/api/mobile-access/session-handoff",
        headers={**RELAY, "accept-language": "zh-CN,zh;q=0.9"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == WEB_SESSION_TTL_SECONDS
    assert body["handoff_url"].startswith("https://api.puregamma.ai/auth/mobile/web-session/consume?code=")

    path = body["handoff_url"].replace("https://api.puregamma.ai", "")
    consumed = api_client.get(path, follow_redirects=False)
    assert consumed.status_code == 302
    # 手机语言决定落地页；会话 cookie 在这一步才写入，交接码本身不含会话
    assert consumed.headers["location"].endswith("/zh/dashboard")
    assert consumed.cookies.get(get_settings().session_cookie_name)

    # 一次性：同一个码不能再用
    assert api_client.get(path, follow_redirects=False).status_code == 400


def test_handoff_ignores_a_disabled_account(api_client, db, user_factory, relay_login):
    user = user_factory("pending@puregamma.ai")
    user.email_verified_at = None
    db.commit()
    relay_login(pocket_remote_email="pending@puregamma.ai", api_public_url="https://api.puregamma.ai", pocket_rpc_secret="relay-secret")
    response = api_client.post("/api/mobile-access/session-handoff", headers=RELAY)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REMOTE_LOGIN_ACCOUNT_MISSING"
