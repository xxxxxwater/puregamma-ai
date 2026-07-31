"""Contract tests for the /portfolio API surface (P0-7)."""

from __future__ import annotations

import json

import pytest

from apps.api.config import Settings
from apps.api.services import cex_connection_service, portfolio_service
from apps.api.services.cex_connection_service import connect_cex
from packages.database.models import AccountSnapshot
from tests.conftest import auth_headers

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def json(self):
        return self.payload


@pytest.fixture()
def portfolio_api_env(monkeypatch):
    settings = Settings(portfolio_token_encryption_key=FERNET_KEY)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(cex_connection_service, "get_settings", lambda: settings)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/v3/account"):
            return FakeResponse({
                "canTrade": False,
                "canWithdraw": False,
                "permissions": ["SPOT"],
                "balances": [
                    {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                    {"asset": "USDT", "free": "1200", "locked": "0"},
                ],
            })
        if url.endswith("/api/v3/ticker/price"):
            return FakeResponse({"symbol": "BTCUSDT", "price": "60000.00"})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("packages.data.cex_private.base.requests.get", fake_get)


@pytest.mark.contract
def test_portfolio_snapshot_api_contract(api_client, db, pro_user, portfolio_api_env):
    connect = api_client.post(
        "/portfolio/cex/connect",
        headers=auth_headers(pro_user),
        json={"venue": "binance", "api_key": "binance-key", "api_secret": "binance-secret"},
    )
    assert connect.status_code == 200

    response = api_client.get("/portfolio", headers=auth_headers(pro_user))
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["nav"] == pytest.approx(37200.0)
    # Only the latest snapshot per account is reflected in the summary rows.
    assert len(body["accounts"]) == 1
    assert body["accounts"][0]["provider"] == "binance"
    assert body["accounts"][0]["nav"] == pytest.approx(37200.0)
    assert len(body["connections"]) == 1
    assert body["connections"][0]["provider"] == "binance"


@pytest.mark.contract
def test_user_a_cannot_read_user_b_portfolio_contract(api_client, db, pro_user, normal_user, portfolio_api_env):
    account = connect_cex(db, pro_user, "binance", "binance-key", "binance-secret")

    foreign_view = api_client.get("/portfolio", headers=auth_headers(normal_user))
    assert foreign_view.status_code == 200
    assert foreign_view.json()["connected"] is False
    assert foreign_view.json()["accounts"] == []

    sync = api_client.post(f"/portfolio/accounts/{account.id}/sync", headers=auth_headers(normal_user))
    assert sync.status_code == 404
    delete = api_client.delete(f"/portfolio/accounts/{account.id}", headers=auth_headers(normal_user))
    assert delete.status_code == 404


@pytest.mark.contract
def test_partial_data_warning_contract(api_client, db, pro_user, portfolio_api_env):
    account = connect_cex(db, pro_user, "binance", "binance-key", "binance-secret")
    snapshot = db.query(AccountSnapshot).filter_by(account_id=account.id).one()
    snapshot.stale = True
    db.commit()

    body = api_client.get("/portfolio", headers=auth_headers(pro_user)).json()
    assert body["stale"] is True
    connection_row = next(item for item in body["connections"] if item["provider"] == "binance")
    assert connection_row["status"] == "STALE"
    context = portfolio_service.portfolio_context(db, pro_user.id)
    assert context["stale"] is True
