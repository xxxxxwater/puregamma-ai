from __future__ import annotations

from apps.api.services.portfolio_service import autopilot_view, connect_hyperliquid, disconnect_account, portfolio_view, run_autopilot_review, sync_account, update_autopilot


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "marginSummary": {"accountValue": "12500.50", "totalMarginUsed": "2500.25"},
            "assetPositions": [{"position": {"coin": "BTC", "szi": "0.1", "entryPx": "60000", "markPx": "62000", "unrealizedPnl": "200", "leverage": {"value": 2}}}],
        }


def test_hyperliquid_read_only_connection_builds_real_nav(db, demo_user, monkeypatch):
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


def test_portfolio_autopilot_is_persisted_as_research_only(db, demo_user):
    result = update_autopilot(db, demo_user, {"enabled": True, "cadence": "weekly", "long_gamma_watch": False})
    assert result["config"]["enabled"] is True
    assert result["config"]["cadence"] == "weekly"
    assert result["execution"] == "RESEARCH_ONLY"
    assert autopilot_view(db, demo_user)["config"]["long_gamma_watch"] is False


def test_multi_account_nav_history_uses_latest_value_for_every_account(db, demo_user, monkeypatch):
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


def test_autopilot_review_persists_concentration_and_disconnects(db, demo_user, monkeypatch):
    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", lambda *args, **kwargs: _Response())
    account = connect_hyperliquid(db, demo_user, "0x" + "3" * 40)
    sync_account(db, demo_user, account)
    update_autopilot(db, demo_user, {"enabled": True, "long_gamma_watch": False})
    review = run_autopilot_review(db, demo_user)
    assert review["last_review"] is not None
    assert review["concentration"]["BTC"] > 0
    assert review["execution"] == "RESEARCH_ONLY"
    disconnect_account(db, demo_user, account)
    assert portfolio_view(db, demo_user)["connected"] is False
