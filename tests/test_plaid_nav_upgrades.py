"""Plaid NAV entitlement upgrades: real-time Balance, Liabilities (net NAV),
and Transactions Refresh — all with honest degradation."""

from __future__ import annotations

import pytest

from apps.api.config import Settings
from apps.api.services import portfolio_service
from packages.database.models import ExchangeConnection, TradingAccount


class FakeResponse:
    def __init__(self, payload, status=200):
        import copy

        self._payload = copy.deepcopy(payload)
        self.status_code = status

    def json(self):
        import copy

        # Each caller gets a fresh copy: the service legitimately mutates the
        # decoded payload (e.g. merging realtime balances), and tests must not
        # leak that mutation into later responses.
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


def _plaid_account(db, user):
    account = TradingAccount(
        user_id=user.id, name="Plaid", venue="PLAID", account_type="READ_ONLY",
        base_currency="USD", status="ACTIVE", permissions_json={},
    )
    db.add(account)
    db.flush()
    connection = ExchangeConnection(
        user_id=user.id, account_id=account.id, adapter="plaid",
        environment="production", status="CONNECTED",
        metadata_json={"plaid_cash_transactions_requested": True},
    )
    db.add(connection)
    db.commit()
    return account


HOLDINGS = {
    "request_id": "r1",
    "accounts": [
        {"account_id": "acc1", "name": "Brokerage", "subtype": "brokerage",
         "balances": {"current": 1000.0, "available": 200.0}}
    ],
    "holdings": [
        {"security_id": "s1", "account_id": "acc1", "quantity": 1, "institution_price": 1000, "institution_value": 1000}
    ],
    "securities": [{"security_id": "s1", "ticker_symbol": "VTI", "type": "equity", "close_price": 990}],
}


def _patch_common(monkeypatch, user, account, extra=None):
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: Settings(plaid_client_id="id", plaid_secret="secret", plaid_env="production"))
    monkeypatch.setattr(portfolio_service, "decrypt_token", lambda ciphertext: "access-token")
    monkeypatch.setattr(portfolio_service, "_update_plaid_webhook", lambda connection, token: None)
    calls = []

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        calls.append(path)
        if path == "/investments/holdings/get":
            return FakeResponse(HOLDINGS)
        for suffix, response in (extra or {}).items():
            if path == suffix:
                return response
        raise AssertionError(f"unexpected plaid call {path}")

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    return calls


def test_realtime_balance_overrides_holdings_balances(api_client, db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    realtime = {"accounts": [{"account_id": "acc1", "name": "Brokerage", "subtype": "brokerage",
                              "balances": {"current": 1500.0, "available": 300.0}}]}
    calls = _patch_common(monkeypatch, demo_user, account, {"/accounts/balance/get": FakeResponse(realtime)})
    portfolio_service.sync_account(db, demo_user, account, include_transactions=False)
    assert "/accounts/balance/get" in calls
    view = portfolio_service.portfolio_view(db, demo_user)
    summary = next(item for item in view["accounts"] if item["id"] == account.id)
    assert summary["nav"] == 1500.0
    assert summary["available_cash"] == 300.0


def test_realtime_balance_failure_falls_back(api_client, db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    _patch_common(monkeypatch, demo_user, account, {"/accounts/balance/get": FakeResponse({"error_code": "PRODUCT_NOT_ENABLED"}, status=400)})
    portfolio_service.sync_account(db, demo_user, account, include_transactions=False)
    view = portfolio_service.portfolio_view(db, demo_user)
    summary = next(item for item in view["accounts"] if item["id"] == account.id)
    assert summary["nav"] == 1000.0  # holdings-derived value survives


def test_liabilities_feed_net_nav(api_client, db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    monkeypatch.setattr(
        portfolio_service, "get_settings",
        lambda: Settings(plaid_client_id="id", plaid_secret="secret", plaid_env="production", plaid_liabilities_enabled=True),
    )
    liabilities = {
        "request_id": "r2",
        "liabilities": {
            "credit": {"acc1": {"balances": {"current": 250.0}, "last_statement_balance": 240.0, "aprs": []}},
            "mortgage": {},
            "student": {},
        },
    }
    monkeypatch.setattr(portfolio_service, "decrypt_token", lambda ciphertext: "access-token")
    monkeypatch.setattr(portfolio_service, "_update_plaid_webhook", lambda connection, token: None)

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        if path == "/investments/holdings/get":
            return FakeResponse(HOLDINGS)
        if path == "/accounts/balance/get":
            return FakeResponse({"error_code": "X"}, status=400)
        if path == "/liabilities/get":
            return FakeResponse(liabilities)
        raise AssertionError(path)

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    portfolio_service.sync_account(db, demo_user, account, include_transactions=False)
    view = portfolio_service.portfolio_view(db, demo_user)
    assert view["liabilities"] == 250.0
    assert view["net_nav"] == 750.0
    summary = next(item for item in view["accounts"] if item["id"] == account.id)
    assert summary["liabilities"] == 250.0
    assert summary["net_nav"] == 750.0
    assert summary["liabilities_breakdown"][0]["type"] == "credit_card"


def test_liabilities_product_gap_degrades(api_client, db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    monkeypatch.setattr(
        portfolio_service, "get_settings",
        lambda: Settings(plaid_client_id="id", plaid_secret="secret", plaid_env="production", plaid_liabilities_enabled=True),
    )
    monkeypatch.setattr(portfolio_service, "decrypt_token", lambda ciphertext: "access-token")
    monkeypatch.setattr(portfolio_service, "_update_plaid_webhook", lambda connection, token: None)

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        if path == "/investments/holdings/get":
            return FakeResponse(HOLDINGS)
        if path == "/accounts/balance/get":
            return FakeResponse({"error_code": "X"}, status=400)
        if path == "/liabilities/get":
            return FakeResponse({"error_code": "PRODUCT_NOT_ENABLED"}, status=400)
        raise AssertionError(path)

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    portfolio_service.sync_account(db, demo_user, account, include_transactions=False)
    view = portfolio_service.portfolio_view(db, demo_user)
    assert view["liabilities"] is None
    assert view["net_nav"] is None
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    assert connection.metadata_json["plaid_liabilities_status"] == "product_not_enabled"


def test_transactions_refresh_flow(api_client, db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    monkeypatch.setattr(
        portfolio_service, "get_settings",
        lambda: Settings(plaid_client_id="id", plaid_secret="secret", plaid_env="production",
                         plaid_cash_transactions_enabled=True, plaid_transactions_refresh_enabled=True),
    )
    monkeypatch.setattr(portfolio_service, "decrypt_token", lambda ciphertext: "access-token")
    calls = []

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        calls.append(path)
        return FakeResponse({"request_id": "r3"})

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    result = portfolio_service.request_plaid_transactions_refresh(db, demo_user, account)
    assert result["status"] == "refresh_requested"
    assert calls == ["/transactions/refresh"]
    # Immediate re-request is rate limited.
    with pytest.raises(portfolio_service.PlaidRefreshRateLimited):
        portfolio_service.request_plaid_transactions_refresh(db, demo_user, account)


def test_transactions_refresh_requires_consent(api_client, db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    connection.metadata_json = {"plaid_cash_transactions_requested": False}
    db.commit()
    monkeypatch.setattr(
        portfolio_service, "get_settings",
        lambda: Settings(plaid_client_id="id", plaid_secret="secret", plaid_env="production",
                         plaid_cash_transactions_enabled=True),
    )
    with pytest.raises(portfolio_service.PlaidRefreshUnsupported):
        portfolio_service.request_plaid_transactions_refresh(db, demo_user, account)
