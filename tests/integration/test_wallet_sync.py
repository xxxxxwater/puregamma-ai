"""Contract tests for public wallet connections (Hyperliquid/EVM) (P0-7).

The wallet service/router exists; these tests pin address validation,
stablecoin-aware NAV, and tenant scoping.
"""

from __future__ import annotations

import pytest

from apps.api.services import portfolio_service
from packages.database.models import TradingAccount
from tests.conftest import auth_headers


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.fixture()
def hyperliquid_transport(monkeypatch):
    def fake_post(url, json=None, timeout=None, **kwargs):
        request_type = (json or {}).get("type")
        if request_type == "clearinghouseState":
            return FakeResponse({"marginSummary": {"accountValue": "5000", "totalMarginUsed": "1000"}, "assetPositions": []})
        if request_type == "spotClearinghouseState":
            return FakeResponse({"balances": [{"coin": "USDC", "total": "1000", "entryNtl": "0"}]})
        if request_type == "allMids":
            return FakeResponse({"BTC": "60000"})
        raise AssertionError(f"unexpected info type {request_type}")

    monkeypatch.setattr("apps.api.services.portfolio_service.requests.post", fake_post)


@pytest.mark.contract
def test_add_wallet_rejects_invalid_address_contract(api_client, db, pro_user, hyperliquid_transport):
    response = api_client.post(
        "/portfolio/hyperliquid/connect",
        headers=auth_headers(pro_user),
        json={"address": "0xnot-a-real-address"},
    )
    assert response.status_code == 400
    assert db.query(TradingAccount).filter_by(user_id=pro_user.id, venue="HYPERLIQUID").count() == 0
    with pytest.raises(ValueError):
        portfolio_service.connect_hyperliquid(db, pro_user, "0xZZZZ" + "1" * 36)


@pytest.mark.contract
def test_sync_wallet_balances_contract(db, pro_user, hyperliquid_transport):
    account = portfolio_service.connect_hyperliquid(db, pro_user, "0x" + "1" * 40)
    portfolio_service.sync_account(db, pro_user, account)
    view = portfolio_service.portfolio_view(db, pro_user)
    # Perp equity 5000 plus 1000 spot USDC (stablecoin priced at 1.0).
    assert view["nav"] == pytest.approx(6000.0)
    assert view["available_cash"] == pytest.approx(5000.0)


@pytest.mark.contract
def test_wallet_owner_scope_contract(api_client, db, pro_user, normal_user, hyperliquid_transport):
    account = portfolio_service.connect_hyperliquid(db, pro_user, "0x" + "3" * 40)
    portfolio_service.sync_account(db, pro_user, account)

    foreign_view = api_client.get("/portfolio", headers=auth_headers(normal_user))
    assert foreign_view.status_code == 200
    assert foreign_view.json()["connected"] is False
    assert foreign_view.json()["accounts"] == []

    sync = api_client.post(f"/portfolio/accounts/{account.id}/sync", headers=auth_headers(normal_user))
    assert sync.status_code == 404
    delete = api_client.delete(f"/portfolio/accounts/{account.id}", headers=auth_headers(normal_user))
    assert delete.status_code == 404
    with pytest.raises(LookupError):
        portfolio_service.sync_account(db, normal_user, account)
