from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from apps.api.services import portfolio_service
from packages.database.models import ExchangeConnection, PortfolioInvestmentTransaction, TradingAccount


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


def _plaid_account(db, user, *, item_id: str = "item-test") -> TradingAccount:
    account = TradingAccount(
        user_id=user.id,
        name="Plaid test",
        venue="PLAID",
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
        permissions_json={"read_positions": True, "trade": False, "withdraw": False, "transfer": False},
    )
    db.add(account)
    db.flush()
    db.add(
        ExchangeConnection(
            user_id=user.id,
            account_id=account.id,
            adapter="plaid",
            environment="production",
            credential_ciphertext="encrypted",
            status="CONNECTED",
            metadata_json={"item_id": item_id},
        )
    )
    db.commit()
    return account


def test_plaid_link_requests_optional_cash_transactions_without_filtering_investments(monkeypatch, demo_user):
    captured: dict = {}
    settings = SimpleNamespace(
        plaid_client_id="client",
        plaid_secret="secret",
        plaid_env="production",
        plaid_redirect_uri="https://puregamma.ai/portfolio",
        plaid_webhook_url="https://api.puregamma.ai/portfolio/plaid/webhook",
        plaid_cash_transactions_enabled=True,
    )
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        captured.update({"path": path, "payload": payload})
        return _Response({"link_token": "link-production-test"})

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    assert portfolio_service.plaid_link_token(demo_user) == "link-production-test"
    assert captured["path"] == "/link/token/create"
    assert captured["payload"]["products"] == ["investments"]
    assert captured["payload"]["optional_products"] == ["transactions"]
    assert captured["payload"]["transactions"] == {"days_requested": 730}
    assert captured["payload"]["webhook"] == settings.plaid_webhook_url


def test_plaid_connection_records_the_transactions_consent_at_link_time(monkeypatch, demo_user):
    captured: dict = {}
    settings = SimpleNamespace(plaid_env="production", plaid_client_id="client", plaid_secret="secret", plaid_cash_transactions_enabled=False)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(portfolio_service, "_plaid_request", lambda *args, **kwargs: _Response({"item_id": "item-1", "access_token": "access-1"}))
    monkeypatch.setattr(portfolio_service, "_update_plaid_webhook", lambda *args, **kwargs: None)
    account = SimpleNamespace(id="account-1")

    def fake_account(db, user, venue, name, metadata, token):
        captured.update({"venue": venue, "metadata": metadata, "token": token})
        return account

    monkeypatch.setattr(portfolio_service, "_account", fake_account)
    monkeypatch.setattr(portfolio_service, "_connection", lambda *args: SimpleNamespace())
    portfolio_service.connect_plaid(SimpleNamespace(commit=lambda: None), demo_user, "public-token")
    assert captured["venue"] == "PLAID"
    assert captured["metadata"]["plaid_cash_transactions_requested"] is False


def test_plaid_cash_transaction_sync_persists_cursor_and_applies_removed_rows(db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    calls: list[dict] = []
    responses = iter(
        [
            _Response(
                {
                    "added": [
                        {
                            "transaction_id": "cash-1",
                            "account_id": "plaid-cash-account",
                            "date": "2026-07-20",
                            "merchant_name": "Coffee Shop",
                            "amount": 4.5,
                            "iso_currency_code": "USD",
                            "pending": False,
                            "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_COFFEE"},
                        }
                    ],
                    "modified": [],
                    "removed": [],
                    "has_more": False,
                    "next_cursor": "cursor-1",
                    "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE",
                }
            ),
            _Response(
                {
                    "added": [],
                    "modified": [],
                    "removed": [{"transaction_id": "cash-1"}],
                    "has_more": False,
                    "next_cursor": "cursor-2",
                    "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE",
                }
            ),
        ]
    )

    def fake_request(path, access_token=None, *, payload=None, timeout=45):
        calls.append({"path": path, "payload": payload})
        return next(responses)

    monkeypatch.setattr(portfolio_service, "_plaid_request", fake_request)
    assert portfolio_service._sync_plaid_cash_transactions(db, account, "access-token") == 1
    row = db.query(PortfolioInvestmentTransaction).filter_by(account_id=account.id, external_id="cash:cash-1").one()
    assert row.name == "Coffee Shop"
    assert row.amount == 4.5
    assert calls[0]["payload"]["cursor"] is None
    assert portfolio_service._connection(db, account).metadata_json["plaid_transactions_cursor"] == "cursor-1"

    assert portfolio_service._sync_plaid_cash_transactions(db, account, "access-token") == 0
    assert db.query(PortfolioInvestmentTransaction).filter_by(account_id=account.id, external_id="cash:cash-1").count() == 0
    assert calls[1]["payload"]["cursor"] == "cursor-1"


def test_plaid_investment_activity_is_scoped_to_the_owner(db, demo_user, user_factory, monkeypatch):
    account = _plaid_account(db, demo_user)
    other = user_factory("plaid-other@example.com")
    other_account = _plaid_account(db, other, item_id="item-other")
    db.add(
        PortfolioInvestmentTransaction(
            user_id=other.id,
            account_id=other_account.id,
            provider="plaid",
            external_id="investment:not-visible",
            provider_account_id="other",
            posted_date=date(2026, 7, 20),
            name="Other user transaction",
            transaction_type="buy",
        )
    )
    db.commit()
    monkeypatch.setattr(
        portfolio_service,
        "_plaid_request",
        lambda *args, **kwargs: _Response(
            {
                "investment_transactions": [
                    {
                        "investment_transaction_id": "investment-1",
                        "account_id": "investment-account",
                        "security_id": "security-1",
                        "date": "2026-07-21",
                        "name": "Buy ACME",
                        "type": "buy",
                        "quantity": 2,
                        "price": 12.5,
                        "amount": 25,
                        "fees": 0.1,
                        "iso_currency_code": "USD",
                    }
                ],
                "securities": [{"security_id": "security-1", "ticker_symbol": "ACME", "type": "equity"}],
                "total_investment_transactions": 1,
            }
        ),
    )
    portfolio_service._sync_plaid_investment_transactions(db, account, "access-token", {})
    rows = portfolio_service.plaid_investment_transactions(db, demo_user)
    assert len(rows) == 1
    assert rows[0]["account_id"] == account.id
    assert rows[0]["symbol"] == "ACME"


def test_plaid_refresh_is_throttled_per_connection(db, demo_user, monkeypatch):
    account = _plaid_account(db, demo_user)
    settings = SimpleNamespace(plaid_investments_refresh_min_minutes=15)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(portfolio_service, "decrypt_token", lambda _value: "access-token")
    monkeypatch.setattr(portfolio_service, "_plaid_request", lambda *args, **kwargs: _Response({"request_id": "refresh-1"}))

    result = portfolio_service.request_plaid_investments_refresh(db, demo_user, account)
    assert result["status"] == "refresh_requested"
    assert result["retry_after_seconds"] == 900
    with pytest.raises(portfolio_service.PlaidRefreshRateLimited):
        portfolio_service.request_plaid_investments_refresh(db, demo_user, account)


def test_plaid_webhook_signature_checks_key_body_and_timestamp(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key())
    body = b'{"webhook_type":"HOLDINGS","item_id":"item-test","environment":"production"}'
    signed = jwt.encode(
        {
            "iat": int(time.time()),
            "request_body_sha256": hashlib.sha256(body).hexdigest(),
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "plaid-key-test"},
    )
    monkeypatch.setattr(portfolio_service, "_plaid_request", lambda *args, **kwargs: _Response({"key": json.loads(public_jwk)}))

    portfolio_service.verify_plaid_webhook(body, signed)
    with pytest.raises(portfolio_service.PlaidWebhookVerificationError):
        portfolio_service.verify_plaid_webhook(body + b"x", signed)
