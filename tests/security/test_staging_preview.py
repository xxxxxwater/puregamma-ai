from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from apps.api.config import Settings, validate_staging_settings
from apps.api.routers import auth, billing, stripe_webhook


def _staging_settings() -> Settings:
    origin = "https://preview.example.test"
    return Settings(
        app_environment="staging",
        site_url=origin,
        cors_origins=(origin,),
        session_cookie_domain=None,
        database_url="sqlite:////tmp/preview.db",
        redis_url="redis://127.0.0.1:16379/0",
        jwt_secret="j" * 40,
        session_secret="s" * 40,
        encryption_master_key="e" * 40,
        internal_runtime_secret="r" * 40,
        metrics_bearer_token="m" * 40,
        auth_allow_demo_fallback=False,
        enable_mock_agent=False,
        enable_mock_market_data=False,
        enable_mock_data_sources=False,
        imessage_provider="disabled",
        live_trading_enabled=False,
        nautilus_live_trading_enabled=False,
        nautilus_allow_live_order=False,
        nautilus_allow_withdrawal=False,
        nautilus_allow_transfer=False,
    )


def test_staging_requires_isolated_secure_configuration() -> None:
    settings = _staging_settings()
    validate_staging_settings(settings)
    for change in (
        {"auth_allow_demo_fallback": True},
        {"session_cookie_domain": ".example.test"},
        {"site_url": "http://preview.example.test"},
        {"jwt_secret": "dev-only-change-me"},
        {"live_trading_enabled": True},
    ):
        with pytest.raises(RuntimeError, match="Invalid staging configuration"):
            validate_staging_settings(replace(settings, **change))


def test_staging_rejects_mock_login_and_paid_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(app_environment="staging", billing_mode="mock")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(billing, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as login:
        auth.mock_login(auth.MockLoginRequest(email="existing@example.test"), Response(), None)
    assert login.value.status_code == 404
    with pytest.raises(HTTPException) as upgrade:
        billing.mock_upgrade(billing.PlanRequest(plan_name="Max"), None, None)
    assert upgrade.value.status_code == 404


def test_staging_rejects_unsigned_mock_stripe_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stripe_webhook,
        "get_settings",
        lambda: SimpleNamespace(app_environment="staging", billing_mode="mock"),
    )
    with pytest.raises(HTTPException) as webhook:
        asyncio.run(stripe_webhook.stripe_webhook(None, None, None))
    assert webhook.value.status_code == 404
