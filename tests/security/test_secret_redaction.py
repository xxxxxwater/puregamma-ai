from __future__ import annotations

import json

import pytest

from apps.api.config import Settings
from apps.api.services import cex_connection_service, portfolio_service
from packages.database.models import ExchangeConnection
from tests.conftest import auth_headers

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="


def test_auth_me_does_not_return_bearer_token(api_client, demo_user):
    response = api_client.get("/me", headers=auth_headers(demo_user))

    assert response.status_code == 200
    assert "access_token" not in response.json()["user"]


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


@pytest.mark.contract
def test_plaid_access_token_not_returned_contract(api_client, db, pro_user, monkeypatch):
    settings = Settings(
        plaid_env="sandbox",
        plaid_client_id="client",
        plaid_secret="secret",
        portfolio_token_encryption_key=FERNET_KEY,
    )
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        if path == "/item/public_token/exchange":
            return _FakeResponse({"access_token": "access-sandbox-secret", "item_id": "item-1"})
        if path == "/investments/holdings/get":
            return _FakeResponse({"accounts": [], "holdings": [], "securities": []})
        raise AssertionError(f"unexpected plaid path {path}")

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    from apps.api.routers import portfolio as portfolio_router

    monkeypatch.setattr(portfolio_router, "_enqueue_plaid_history_sync", lambda account_id: None)
    response = api_client.post(
        "/portfolio/plaid/exchange",
        headers=auth_headers(pro_user),
        json={"public_token": "public-sandbox-token"},
    )
    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "access-sandbox-secret" not in serialized
    assert "credential_ciphertext" not in serialized

    view = api_client.get("/portfolio", headers=auth_headers(pro_user))
    assert view.status_code == 200
    serialized = json.dumps(view.json())
    assert "access-sandbox-secret" not in serialized
    assert "credential_ciphertext" not in serialized


@pytest.mark.contract
def test_exchange_api_key_not_returned_contract(api_client, db, pro_user, monkeypatch):
    settings = Settings(portfolio_token_encryption_key=FERNET_KEY)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(cex_connection_service, "get_settings", lambda: settings)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/v3/account"):
            return _FakeResponse({"canTrade": False, "canWithdraw": False, "permissions": ["SPOT"], "balances": [{"asset": "BTC", "free": "0.5", "locked": "0"}]})
        if url.endswith("/api/v3/ticker/price"):
            return _FakeResponse({"symbol": "BTCUSDT", "price": "60000"})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("packages.data.cex_private.base.requests.get", fake_get)
    response = api_client.post(
        "/portfolio/cex/connect",
        headers=auth_headers(pro_user),
        json={"venue": "binance", "api_key": "binance-key", "api_secret": "binance-secret", "passphrase": "should-not-echo"},
    )
    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "binance-secret" not in serialized
    assert "should-not-echo" not in serialized
    assert "credential_ciphertext" not in serialized

    connection = db.query(ExchangeConnection).filter_by(adapter="binance").one()
    assert "binance-secret" not in connection.credential_ciphertext

    view = api_client.get("/portfolio", headers=auth_headers(pro_user))
    serialized = json.dumps(view.json())
    assert "binance-secret" not in serialized
    assert "should-not-echo" not in serialized
    assert "credential_ciphertext" not in serialized
