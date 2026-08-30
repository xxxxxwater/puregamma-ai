from __future__ import annotations

import pytest

from apps.api.services.portfolio_service import PortfolioAccessError, connect_hyperliquid, disconnect_account, portfolio_view, sync_account
from apps.api.services.billing_service import mock_upgrade


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "marginSummary": {"accountValue": "12500.50", "totalMarginUsed": "2500.25"},
            "assetPositions": [{"position": {"coin": "BTC", "szi": "0.1", "entryPx": "60000", "markPx": "62000", "unrealizedPnl": "200", "leverage": {"value": 2}}}],
        }


def test_hyperliquid_read_only_connection_builds_real_nav(db, demo_user, monkeypatch):
    mock_upgrade(db, demo_user.id, "Max")
    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", lambda *args, **kwargs: _Response())
    account = connect_hyperliquid(db, demo_user, "0x" + "1" * 40)
    sync_account(db, demo_user, account)
    result = portfolio_view(db, demo_user)
    assert result["connected"] is True
    assert result["nav"] == 12500.50
    assert result["available_cash"] == 10000.25
    assert result["connections"][0]["provider"] == "hyperliquid"
    assert account.permissions_json["trade"] is False
    assert account.permissions_json["withdraw"] is False


def test_multi_account_nav_history_uses_latest_value_for_every_account(db, demo_user, monkeypatch):
    mock_upgrade(db, demo_user.id, "Max")
    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", lambda *args, **kwargs: _Response())
    first = connect_hyperliquid(db, demo_user, "0x" + "1" * 40)
    second = connect_hyperliquid(db, demo_user, "0x" + "2" * 40)
    sync_account(db, demo_user, first)
    sync_account(db, demo_user, second)
    sync_account(db, demo_user, first)
    result = portfolio_view(db, demo_user)
    assert result["nav"] == 25001.0
    assert result["nav_history"][-1]["nav"] == 25001.0
    assert all(point["nav"] == 25001.0 for point in result["nav_history"])


def test_free_plan_allows_one_portfolio_connection(db, normal_user, monkeypatch):
    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", lambda *args, **kwargs: _Response())
    account = connect_hyperliquid(db, normal_user, "0x" + "1" * 40)
    sync_account(db, normal_user, account)
    assert portfolio_view(db, normal_user)["connected"] is True
    # Reconnecting the same wallet reuses the account and never hits the limit.
    connect_hyperliquid(db, normal_user, "0x" + "1" * 40)
    with pytest.raises(PortfolioAccessError) as excinfo:
        connect_hyperliquid(db, normal_user, "0x" + "2" * 40)
    assert excinfo.value.code == "PORTFOLIO_LIMIT_REACHED"
    assert excinfo.value.context == {"plan": "Free", "active_count": 1, "max_portfolios": 1}


def test_disconnect_account_removes_connection_from_view(db, demo_user, monkeypatch):
    mock_upgrade(db, demo_user.id, "Max")
    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", lambda *args, **kwargs: _Response())
    account = connect_hyperliquid(db, demo_user, "0x" + "3" * 40)
    sync_account(db, demo_user, account)
    assert portfolio_view(db, demo_user)["connected"] is True
    disconnect_account(db, demo_user, account)
    assert portfolio_view(db, demo_user)["connected"] is False
