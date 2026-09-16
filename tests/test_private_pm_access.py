"""Private Binance PM must never leak via a public portfolio session."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.api.routers.private_pm import _allowed_user, _snapshot


def user(email: str, *, verified: bool = True, provider: str = "google"):
    return SimpleNamespace(email=email, email_verified_at=datetime.now(timezone.utc) if verified else None, auth_provider=provider)


def test_authorization_rejects_unconfigured_and_partial_list(monkeypatch):
    monkeypatch.delenv("RISKBOT_PM_ALLOWED_EMAILS", raising=False)
    assert not _allowed_user(user("one@example.com"))
    monkeypatch.setenv("RISKBOT_PM_ALLOWED_EMAILS", "one@example.com")
    assert not _allowed_user(user("one@example.com"))


def test_authorization_only_two_verified_real_accounts(monkeypatch):
    monkeypatch.setenv("RISKBOT_PM_ALLOWED_EMAILS", "One@Example.com,two@example.com")
    assert _allowed_user(user("one@example.com"))
    assert _allowed_user(user("TWO@example.com"))
    assert not _allowed_user(user("other@example.com"))
    assert not _allowed_user(user("one@example.com", verified=False))
    assert not _allowed_user(user("one@example.com", provider="mock"))
    monkeypatch.setenv("RISKBOT_PM_ALLOWED_EMAILS", "one@example.com,one@example.com")
    assert not _allowed_user(user("one@example.com"))
    monkeypatch.setenv("RISKBOT_PM_ALLOWED_EMAILS", "one@example.com,two@example.com,other@example.com")
    assert not _allowed_user(user("one@example.com"))


def payload():
    return {
        "source": "binance_pm_classic", "captured_at": datetime.now(timezone.utc).isoformat(),
        "account": {"account_equity_usd": "125000", "btc_wallet_quantity": "2.5", "equity_btc_equivalent": "1.5", "account_status": "NORMAL", "api_secret": "MUST_NOT_LEAK"},
        "balances": [], "positions": [], "orders": [], "orders_captured_at": datetime.now(timezone.utc).isoformat(),
        "coverage": {key: "ok" for key in ("account", "balance", "um_positions", "cm_positions", "um_orders", "um_algo_orders", "cm_orders", "cm_conditional_orders", "margin_orders", "margin_oco_orders")},
        "api_key": "MUST_NOT_LEAK",
    }


def test_private_projection_keeps_actual_btc_distinct_from_nav_equivalent():
    result = _snapshot(payload())
    assert result["account"]["btc_wallet_quantity"] == "2.5"
    assert result["account"]["equity_btc_equivalent"] == "1.5"
    assert "api_secret" not in result["account"]
    assert "api_key" not in result
    assert result["orders"] == []


def test_partial_order_fetch_never_reports_zero_orders():
    raw = payload()
    raw["coverage"]["um_algo_orders"] = "failed"
    result = _snapshot(raw)
    assert result["orders"] is None
    assert result["orders_stale"] is True


def test_missing_core_coverage_fails_closed():
    raw = payload()
    raw["coverage"]["balance"] = "failed"
    with pytest.raises(HTTPException) as exc:
        _snapshot(raw)
    assert exc.value.status_code == 503
