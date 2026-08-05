"""Contract tests for the Plaid Investments connection flow (P0-7).

The Plaid service/router exists; these tests pin the token-handling and
normalization contracts with a mocked Plaid API.
"""

from __future__ import annotations

import json

import pytest

from apps.api.config import Settings
from apps.api.routers import portfolio as portfolio_router
from apps.api.services import portfolio_service
from packages.database.models import AccountSnapshot, ExchangeConnection, PositionSnapshot
from tests.conftest import auth_headers

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="

HOLDINGS_PAYLOAD = {
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


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


@pytest.fixture()
def plaid_env(monkeypatch):
    settings = Settings(
        plaid_env="sandbox",
        plaid_client_id="client",
        plaid_secret="secret",
        portfolio_token_encryption_key=FERNET_KEY,
    )
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        if path == "/link/token/create":
            return FakeResponse({"link_token": "link-sandbox-test-token"})
        if path == "/item/public_token/exchange":
            return FakeResponse({"access_token": "access-sandbox-secret", "item_id": "item-1"})
        if path == "/investments/holdings/get":
            assert access_token == "access-sandbox-secret"
            return FakeResponse(HOLDINGS_PAYLOAD)
        raise AssertionError(f"unexpected plaid path {path}")

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    monkeypatch.setattr(portfolio_router, "_enqueue_plaid_history_sync", lambda account_id: None)


@pytest.mark.contract
def test_create_link_token_mock_contract(api_client, demo_user, plaid_env):
    response = api_client.post("/portfolio/plaid/link-token", headers=auth_headers(demo_user))
    assert response.status_code == 200
    # A Link token is returned without ever exposing server credentials.
    assert response.json()["link_token"] == "link-sandbox-test-token"
    assert "secret" not in json.dumps(response.json())


@pytest.mark.contract
def test_exchange_public_token_encrypts_access_token_contract(api_client, db, pro_user, plaid_env):
    response = api_client.post(
        "/portfolio/plaid/exchange",
        headers=auth_headers(pro_user),
        json={"public_token": "public-sandbox-token", "institution_name": "Test Brokerage"},
    )
    assert response.status_code == 200
    assert "access-sandbox-secret" not in json.dumps(response.json())

    connection = db.query(ExchangeConnection).filter_by(adapter="plaid").one()
    assert connection.credential_ciphertext
    assert "access-sandbox-secret" not in connection.credential_ciphertext
    assert portfolio_service.decrypt_token(connection.credential_ciphertext) == "access-sandbox-secret"


@pytest.mark.contract
def test_plaid_holdings_and_transactions_normalize_contract(api_client, db, pro_user, plaid_env):
    api_client.post(
        "/portfolio/plaid/exchange",
        headers=auth_headers(pro_user),
        json={"public_token": "public-sandbox-token", "institution_name": "Test Brokerage"},
    )
    account_row = db.query(ExchangeConnection).filter_by(adapter="plaid").one()
    snapshot = db.query(AccountSnapshot).filter_by(account_id=account_row.account_id).one()
    assert snapshot.equity == pytest.approx(11000.0)
    assert snapshot.available_margin == pytest.approx(1000.0)
    positions = db.query(PositionSnapshot).filter_by(account_id=account_row.account_id, captured_at=snapshot.captured_at).all()
    assert {row.instrument for row in positions} == {"MSTR", "USD"}


@pytest.mark.contract
def test_disconnect_plaid_deletes_encrypted_token_contract(api_client, db, pro_user, plaid_env):
    api_client.post(
        "/portfolio/plaid/exchange",
        headers=auth_headers(pro_user),
        json={"public_token": "public-sandbox-token", "institution_name": "Test Brokerage"},
    )
    connection = db.query(ExchangeConnection).filter_by(adapter="plaid").one()
    account_id = connection.account_id

    response = api_client.delete(f"/portfolio/accounts/{account_id}", headers=auth_headers(pro_user))
    assert response.status_code == 200
    db.refresh(connection)
    assert connection.status == "DISCONNECTED"
    assert connection.credential_ciphertext is None
    assert response.json()["connected"] is False
