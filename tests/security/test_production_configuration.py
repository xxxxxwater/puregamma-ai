from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from apps.api.config import Settings, validate_production_settings
from apps.api import main


def valid_production_settings() -> Settings:
    return Settings(
        app_environment="production",
        database_url="postgresql+psycopg://puregamma:secret@postgres/puregamma",
        redis_url="redis://redis:6379/0",
        jwt_secret="j" * 32,
        session_secret="s" * 32,
        encryption_master_key="e" * 32,
        internal_runtime_secret="i" * 32,
        nautilus_runtime_secret="n" * 32,
        site_url="https://app.puregamma.ai",
        cors_origins=("https://app.puregamma.ai",),
        session_cookie_domain=".puregamma.ai",
        billing_mode="stripe",
        stripe_secret_key="sk_live_test",
        stripe_webhook_secret="whsec_test",
        stripe_success_url="https://app.puregamma.ai/billing/success",
        stripe_cancel_url="https://app.puregamma.ai/billing/cancel",
        google_oauth_redirect_uri="https://app.puregamma.ai/zh/auth/google/callback",
        mobile_google_oauth_redirect_uri="https://api.puregamma.ai/auth/mobile/google/callback",
        mobile_ibkr_oauth_redirect_uri="https://api.puregamma.ai/portfolio/ibkr/mobile/callback",
        apple_auth_enabled=True,
        apple_client_id="ai.puregamma.ios",
        apple_team_id="APPLE_TEAM",
        apple_key_id="APPLE_KEY",
        apple_private_key="server-only-private-key",
        llm_provider="deepseek",
        deepseek_api_key="server-only-key",
        openai_luna_enabled=False,
        imessage_provider="disabled",
        nautilus_execution_mode="paper",
        enable_mock_market_data=False,
    )


def test_valid_production_configuration_passes():
    validate_production_settings(valid_production_settings())


def test_production_allows_disabled_apple_auth_without_credentials():
    settings = replace(
        valid_production_settings(),
        apple_auth_enabled=False,
        apple_team_id="",
        apple_key_id="",
        apple_private_key="",
    )
    validate_production_settings(settings)


def test_gateway_requires_each_enabled_provider_key():
    settings = replace(
        valid_production_settings(),
        gateway_enabled=True,
        gateway_api_key_pepper="p" * 32,
        gateway_enabled_providers=("deepseek", "glm"),
        gateway_deepseek_api_key="deepseek-key",
    )
    with pytest.raises(RuntimeError, match="GATEWAY_GLM_API_KEY"):
        validate_production_settings(settings)


def test_gateway_with_all_phase_one_provider_keys_passes():
    settings = replace(
        valid_production_settings(),
        gateway_enabled=True,
        gateway_api_key_pepper="p" * 32,
        gateway_deepseek_api_key="deepseek-key",
        gateway_moonshot_api_key="moonshot-key",
        gateway_glm_api_key="glm-key",
    )
    validate_production_settings(settings)


def test_gateway_allows_a_verified_subset_of_providers():
    settings = replace(
        valid_production_settings(),
        gateway_enabled=True,
        gateway_api_key_pepper="p" * 32,
        gateway_enabled_providers=("deepseek",),
        gateway_deepseek_api_key="deepseek-key",
    )
    validate_production_settings(settings)


def test_gateway_rejects_unknown_enabled_provider():
    settings = replace(
        valid_production_settings(),
        gateway_enabled=True,
        gateway_api_key_pepper="p" * 32,
        gateway_enabled_providers=("unregistered",),
    )
    with pytest.raises(RuntimeError, match="unsupported providers"):
        validate_production_settings(settings)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("billing_mode", "mock", "BILLING_MODE"),
        ("llm_provider", "mock", "LLM_PROVIDER"),
        ("enable_mock_agent", True, "Mock Agent"),
        ("enable_mock_market_data", True, "Mock Agent"),
        ("imessage_provider", "mock", "IMESSAGE_PROVIDER"),
        ("apple_private_key", "", "APPLE_CLIENT_ID"),
        ("apns_enabled", True, "APNS"),
        ("nautilus_live_trading_enabled", True, "LIVE trading"),
        ("nautilus_allow_withdrawal", True, "Withdrawal"),
    ],
)
def test_unsafe_production_configuration_fails(field, value, message):
    with pytest.raises(RuntimeError, match=message):
        validate_production_settings(replace(valid_production_settings(), **{field: value}))


def test_production_macos_relay_requires_relay_secret():
    settings = replace(valid_production_settings(), imessage_provider="macos_relay", imessage_relay_secret="")
    with pytest.raises(RuntimeError, match="IMESSAGE_RELAY_SECRET"):
        validate_production_settings(settings)


def test_production_macos_relay_passes_with_secret():
    settings = replace(
        valid_production_settings(),
        imessage_provider="macos_relay",
        imessage_relay_secret="relay-secret",
    )
    validate_production_settings(settings)


def test_production_photon_requires_each_credential():
    settings = replace(valid_production_settings(), imessage_provider="photon")
    with pytest.raises(RuntimeError, match="PHOTON_API_KEY"):
        validate_production_settings(settings)


def test_production_photon_passes_with_full_configuration():
    settings = replace(
        valid_production_settings(),
        imessage_provider="photon",
        photon_api_key="photon-api-key",
        photon_line_id="+14243825596",
        photon_server_url="https://server.photon.codes",
        photon_http_proxy_url="https://imessage-swagger.photon.codes",
        photon_webhook_secret="photon-webhook-secret",
    )
    validate_production_settings(settings)


def test_cookie_authenticated_state_change_requires_approved_origin(monkeypatch):
    settings = valid_production_settings()
    monkeypatch.setattr(main, "settings", settings)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/billing/cancel-subscription",
        "raw_path": b"/billing/cancel-subscription",
        "query_string": b"",
        "headers": [(b"cookie", b"pg_session=fake"), (b"origin", b"https://evil.example")],
        "client": ("127.0.0.1", 1234),
        "server": ("api.puregamma.ai", 443),
    }
    request = Request(scope)

    async def call_next(_: Request):
        return JSONResponse({"ok": True})

    response = asyncio.run(main.cookie_csrf_guard(request, call_next))

    assert response.status_code == 403


def test_cookie_authenticated_state_change_accepts_saas_origin(monkeypatch):
    settings = valid_production_settings()
    monkeypatch.setattr(main, "settings", settings)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/billing/cancel-subscription",
        "raw_path": b"/billing/cancel-subscription",
        "query_string": b"",
        "headers": [(b"cookie", b"pg_session=fake"), (b"origin", b"https://app.puregamma.ai")],
        "client": ("127.0.0.1", 1234),
        "server": ("api.puregamma.ai", 443),
    }
    request = Request(scope)

    async def call_next(_: Request):
        return JSONResponse({"ok": True})

    response = asyncio.run(main.cookie_csrf_guard(request, call_next))

    assert response.status_code == 200
