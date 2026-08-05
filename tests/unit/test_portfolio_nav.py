"""Contract tests for portfolio NAV computation across sources (P0-7).

The NAV service exists (``portfolio_service`` + ``cex_connection_service``);
these tests pin NAV math with fixed test prices for each source type.
"""

from __future__ import annotations

import json

import pytest

from apps.api.config import Settings
from apps.api.services import cex_connection_service, portfolio_service
from apps.api.services.cex_connection_service import connect_cex
from packages.database.models import AccountSnapshot, PositionSnapshot

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode() if isinstance(payload, (dict, list)) else b"{}"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


@pytest.fixture()
def nav_settings(monkeypatch):
    settings = Settings(portfolio_token_encryption_key=FERNET_KEY)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(cex_connection_service, "get_settings", lambda: settings)
    return settings


def _connect_binance(db, user, monkeypatch, state):
    account_payload = {
        "canTrade": False,
        "canWithdraw": False,
        "permissions": ["SPOT"],
        "balances": [
            {"asset": "BTC", "free": "0.5", "locked": "0.1"},
            {"asset": "USDT", "free": "1200", "locked": "0"},
        ],
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/v3/account"):
            if state.get("binance_broken"):
                return FakeResponse({"code": -1000, "msg": "error"}, status_code=500)
            return FakeResponse(account_payload)
        if url.endswith("/api/v3/ticker/price"):
            return FakeResponse({"symbol": "BTCUSDT", "price": "60000.00"})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("packages.data.cex_private.base.requests.get", fake_get)
    return connect_cex(db, user, "binance", "binance-key", "binance-secret")


def _hyperliquid_transport(monkeypatch, *, account_value="5000", margin_used="1000", spot_usdc="1000"):
    def fake_post(url, json=None, timeout=None, **kwargs):
        request_type = (json or {}).get("type")
        if request_type == "clearinghouseState":
            return FakeResponse({"marginSummary": {"accountValue": account_value, "totalMarginUsed": margin_used}, "assetPositions": []})
        if request_type == "spotClearinghouseState":
            return FakeResponse({"balances": [{"coin": "USDC", "total": spot_usdc, "entryNtl": "0"}]})
        if request_type == "allMids":
            return FakeResponse({})
        raise AssertionError(f"unexpected info type {request_type}")

    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", fake_post)


@pytest.mark.contract
def test_plaid_only_nav_contract(db, pro_user, nav_settings, monkeypatch):
    account = portfolio_service._account(db, pro_user, "PLAID", "Plaid", {"item_id": "item-1"}, "access-token")
    holdings_payload = {
        "accounts": [{"account_id": "pa-1", "name": "Brokerage", "subtype": "brokerage", "balances": {"current": 11000.0, "available": 1000.0}}],
        "holdings": [
            {"account_id": "pa-1", "security_id": "s1", "quantity": 10, "institution_price": 1000.0, "institution_value": 10000.0, "cost_basis": 9000.0},
            {"account_id": "pa-1", "security_id": "s2", "quantity": 1000, "institution_price": 1.0, "institution_value": 1000.0, "cost_basis": 1000.0},
        ],
        "securities": [
            {"security_id": "s1", "ticker_symbol": "MSTR", "name": "Strategy", "type": "equity", "close_price": 950.0},
            {"security_id": "s2", "ticker_symbol": "USD", "name": "US Dollar", "type": "cash", "is_cash_equivalent": True, "close_price": 1.0},
        ],
    }
    monkeypatch.setattr(portfolio_service, "_plaid_request", lambda *args, **kwargs: FakeResponse(holdings_payload))
    monkeypatch.setattr(portfolio_service, "_update_plaid_webhook", lambda *args, **kwargs: None)
    portfolio_service._sync_plaid(db, account, include_transactions=False)

    view = portfolio_service.portfolio_view(db, pro_user)
    assert view["connected"] is True
    assert view["nav"] == pytest.approx(11000.0)
    assert view["available_cash"] == pytest.approx(1000.0)


@pytest.mark.contract
def test_cex_only_nav_contract(db, pro_user, nav_settings, monkeypatch):
    _connect_binance(db, pro_user, monkeypatch, {})
    view = portfolio_service.portfolio_view(db, pro_user)
    # 0.6 BTC at the fixed 60000 test price plus 1200 USDT.
    assert view["nav"] == pytest.approx(37200.0)
    assert view["available_cash"] == pytest.approx(1200.0)


@pytest.mark.contract
def test_wallet_only_nav_contract(db, pro_user, nav_settings, monkeypatch):
    _hyperliquid_transport(monkeypatch)
    account = portfolio_service.connect_hyperliquid(db, pro_user, "0x" + "1" * 40)
    portfolio_service.sync_account(db, pro_user, account)
    view = portfolio_service.portfolio_view(db, pro_user)
    # Perp equity 5000 plus 1000 spot USDC stablecoin value.
    assert view["nav"] == pytest.approx(6000.0)


@pytest.mark.contract
def test_mixed_sources_do_not_double_count_duplicate_assets_contract(db, max_user, nav_settings, monkeypatch):
    binance = _connect_binance(db, max_user, monkeypatch, {})
    _hyperliquid_transport(monkeypatch, account_value="6200", margin_used="0", spot_usdc="0")
    hyperliquid = portfolio_service.connect_hyperliquid(db, max_user, "0x" + "2" * 40)
    portfolio_service.sync_account(db, max_user, hyperliquid)

    view = portfolio_service.portfolio_view(db, max_user)
    assert view["nav"] == pytest.approx(37200.0 + 6200.0)
    # BTC from both sources is aggregated into ONE holding row keyed by
    # instrument; NAV history is not replayed on re-sync.
    portfolio_service.sync_account(db, max_user, binance)
    view = portfolio_service.portfolio_view(db, max_user)
    assert view["nav"] == pytest.approx(37200.0 + 6200.0)
    latest = db.query(AccountSnapshot).filter_by(account_id=binance.id).order_by(AccountSnapshot.captured_at.desc()).first()
    assert db.query(PositionSnapshot).filter_by(account_id=binance.id, captured_at=latest.captured_at).count() == 2


@pytest.mark.contract
def test_sync_failure_does_not_overwrite_last_valid_snapshot_contract(db, pro_user, nav_settings, monkeypatch):
    state = {}
    account = _connect_binance(db, pro_user, monkeypatch, state)
    assert db.query(AccountSnapshot).filter_by(account_id=account.id).count() == 1

    state["binance_broken"] = True
    with pytest.raises(Exception):
        portfolio_service.sync_account(db, pro_user, account)

    snapshots = db.query(AccountSnapshot).filter_by(account_id=account.id).all()
    assert len(snapshots) == 1  # failed sync wrote nothing
    view = portfolio_service.portfolio_view(db, pro_user)
    assert view["connected"] is True
    assert view["nav"] == pytest.approx(37200.0)  # previous valid NAV preserved
