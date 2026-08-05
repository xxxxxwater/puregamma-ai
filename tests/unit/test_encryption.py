"""Contract tests for the portfolio credential encryption service (P0-7).

``portfolio_service.encrypt_token`` / ``decrypt_token`` (Fernet) back every
Plaid/IBKR/CEX credential stored on ``ExchangeConnection``. These tests pin
the round-trip, non-determinism, and redaction contracts.
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from apps.api.config import Settings
from apps.api.services import portfolio_service
from packages.database.models import ExchangeConnection, TradingAccount

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="


@pytest.fixture()
def encryption_settings(monkeypatch):
    settings = Settings(portfolio_token_encryption_key=FERNET_KEY)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    return settings


@pytest.mark.contract
def test_secret_encryption_service_contract(encryption_settings):
    plaintext = "exchange-api-secret-123"
    ciphertext = portfolio_service.encrypt_token(plaintext)
    assert ciphertext != plaintext
    assert plaintext not in ciphertext
    # Fernet output is urlsafe-base64 and decrypts with the configured key.
    assert Fernet(FERNET_KEY.encode()).decrypt(ciphertext.encode()).decode() == plaintext


@pytest.mark.contract
def test_encrypted_secret_round_trip_contract(encryption_settings):
    first = portfolio_service.encrypt_token("same-secret")
    second = portfolio_service.encrypt_token("same-secret")
    # Non-deterministic ciphertext, deterministic decryption.
    assert first != second
    assert portfolio_service.decrypt_token(first) == "same-secret"
    assert portfolio_service.decrypt_token(second) == "same-secret"
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        portfolio_service.decrypt_token(Fernet.generate_key().decode())


@pytest.mark.contract
def test_secret_values_are_not_serialized_contract(db, pro_user, encryption_settings):
    account = TradingAccount(
        user_id=pro_user.id,
        name="IBKR test",
        venue="IBKR",
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
    )
    db.add(account)
    db.flush()
    db.add(
        ExchangeConnection(
            user_id=pro_user.id,
            account_id=account.id,
            adapter="ibkr",
            environment="production",
            credential_ciphertext=portfolio_service.encrypt_token("ibkr-access-token-secret"),
            status="CONNECTED",
            metadata_json={"expires_at": 9999999999},
        )
    )
    db.commit()
    view = portfolio_service.portfolio_view(db, pro_user)
    serialized = json.dumps(view)
    assert "ibkr-access-token-secret" not in serialized
    assert "credential_ciphertext" not in serialized
    context = portfolio_service.portfolio_context(db, pro_user.id)
    assert "ibkr-access-token-secret" not in json.dumps(context)
