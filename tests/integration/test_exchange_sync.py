"""Contract tests for read-only private exchange (CEX) sync (P0-7).

The exchange credential service now exists
(``apps.api.services.cex_connection_service`` + ``packages.data.cex_private``);
these tests pin the security and normalization contracts with recorded venue
payloads.
"""

from __future__ import annotations

import json

import pytest

from apps.api.config import Settings
from apps.api.services import cex_connection_service, portfolio_service
from apps.api.services.cex_connection_service import connect_cex
from packages.database.models import AccountSnapshot, ExchangeConnection, TradingAccount

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="

BINANCE_ACCOUNT = {
    "canTrade": False,
    "canWithdraw": False,
    "canDeposit": False,
    "accountType": "SPOT",
    "permissions": ["SPOT"],
    "balances": [
        {"asset": "BTC", "free": "0.5", "locked": "0.1"},
        {"asset": "USDT", "free": "1200", "locked": "0"},
    ],
}

BYBIT_WALLET = {
    "retCode": 0,
    "result": {"list": [{"accountType": "UNIFIED", "coin": [{"coin": "SOL", "walletBalance": "10", "usdValue": "1500", "locked": "0"}]}]},
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def json(self):
        return self.payload


@pytest.fixture()
def exchange_env(monkeypatch):
    settings = Settings(portfolio_token_encryption_key=FERNET_KEY)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(cex_connection_service, "get_settings", lambda: settings)
    state = {"bybit_broken": False, "bybit_withdraw_scope": False}

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/v3/account"):
            return FakeResponse(BINANCE_ACCOUNT)
        if url.endswith("/api/v3/ticker/price"):
            return FakeResponse({"symbol": "BTCUSDT", "price": "60000.00"})
        if "/v5/user/query-api" in url:
            permissions = {"ContractTrade": [], "Spot": [], "Wallet": ["AccountTransfer"] if state["bybit_withdraw_scope"] else []}
            return FakeResponse({"retCode": 0, "result": {"apiKey": "k", "readOnly": 0 if state["bybit_withdraw_scope"] else 1, "permissions": permissions}})
        if "/v5/account/wallet-balance" in url:
            if state["bybit_broken"]:
                return FakeResponse({"retCode": 10016, "retMsg": "internal error"}, status_code=500)
            return FakeResponse(BYBIT_WALLET)
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("packages.data.cex_private.base.requests.get", fake_get)
    return state


@pytest.mark.contract
def test_read_only_exchange_key_saved_encrypted_contract(db, pro_user, exchange_env):
    account = connect_cex(db, pro_user, "binance", "binance-key", "binance-secret")
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    # Encrypted at rest…
    assert connection.credential_ciphertext
    assert "binance-secret" not in connection.credential_ciphertext
    stored = json.loads(portfolio_service.decrypt_token(connection.credential_ciphertext))
    assert stored["api_secret"] == "binance-secret"
    # …and redacted from every serialized surface.
    assert "binance-secret" not in json.dumps(portfolio_service.portfolio_view(db, pro_user))
    assert "binance-secret" not in json.dumps(connection.metadata_json)


@pytest.mark.contract
def test_withdrawal_permission_warning_contract(db, max_user, exchange_env):
    exchange_env["bybit_withdraw_scope"] = True
    account = connect_cex(db, max_user, "bybit", "bybit-key", "bybit-secret")
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    check = connection.metadata_json["permission_check"]
    # Keys carrying withdrawal scopes are surfaced as a verified warning flag;
    # the platform still never calls any write endpoint with them.
    assert check["permissions_verified"] is True
    assert check["can_withdraw"] is True
    assert account.permissions_json["withdraw"] is False
    assert account.permissions_json["trade"] is False


@pytest.mark.contract
def test_exchange_balances_normalize_and_failure_isolated_contract(db, max_user, exchange_env):
    binance = connect_cex(db, max_user, "binance", "binance-key", "binance-secret")
    bybit = connect_cex(db, max_user, "bybit", "bybit-key", "bybit-secret")
    binance_snapshot = db.query(AccountSnapshot).filter_by(account_id=binance.id).one()
    assert binance_snapshot.equity == pytest.approx(37200.0)
    bybit_snapshot = db.query(AccountSnapshot).filter_by(account_id=bybit.id).one()
    assert bybit_snapshot.equity == pytest.approx(1500.0)

    exchange_env["bybit_broken"] = True
    with pytest.raises(Exception):
        portfolio_service.sync_account(db, max_user, bybit)
    assert db.query(ExchangeConnection).filter_by(account_id=bybit.id).one().status == "ERROR"

    # The other venue keeps working and its previous snapshot is untouched.
    portfolio_service.sync_account(db, max_user, binance)
    assert db.query(AccountSnapshot).filter_by(account_id=binance.id).count() == 2
    assert db.query(ExchangeConnection).filter_by(account_id=binance.id).one().status == "CONNECTED"


@pytest.mark.contract
def test_private_key_or_seed_phrase_rejected_contract(db, pro_user, exchange_env):
    with pytest.raises(ValueError, match="CEX_KEY_MATERIAL_REJECTED"):
        connect_cex(db, pro_user, "binance", "key", "0x" + "ab" * 32)
    with pytest.raises(ValueError, match="CEX_KEY_MATERIAL_REJECTED"):
        connect_cex(db, pro_user, "bybit", "key", "legal winner thank year wave sausage worth useful legal winner thank yellow")
    assert db.query(TradingAccount).filter_by(user_id=pro_user.id).count() == 0
