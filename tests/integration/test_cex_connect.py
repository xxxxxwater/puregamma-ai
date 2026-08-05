"""Integration tests for private CEX connect → sync → NAV → brief (P0-7).

Adapter HTTP is monkeypatched with recorded Binance/OKX/Bybit payloads, so
the whole flow runs offline: permission probe → encrypted connection →
snapshot + positions → portfolio view/context → disconnect.
"""

from __future__ import annotations

import json

import pytest

from apps.api.config import Settings
from apps.api.services import cex_connection_service, portfolio_service
from apps.api.services.cex_connection_service import connect_cex
from packages.database.models import AccountSnapshot, ExchangeConnection, PositionSnapshot, Report, TradingAccount
from tests.conftest import auth_headers

FERNET_KEY = "1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0="

BINANCE_ACCOUNT = {
    "makerCommission": 10,
    "takerCommission": 10,
    "canTrade": False,
    "canWithdraw": False,
    "canDeposit": False,
    "accountType": "SPOT",
    "permissions": ["SPOT"],
    "balances": [
        {"asset": "BTC", "free": "0.50000000", "locked": "0.10000000"},
        {"asset": "USDT", "free": "1200.00000000", "locked": "0.00000000"},
        {"asset": "SHIB", "free": "9000.00000000", "locked": "0.00000000"},
    ],
}

OKX_BALANCE = {
    "code": "0",
    "msg": "",
    "data": [
        {
            "totalEq": "1900",
            "details": [
                {"availBal": "0.4", "ccy": "ETH", "eq": "0.4", "eqUsd": "1400", "frozenBal": "0"},
                {"availBal": "500", "ccy": "USDT", "eq": "500", "eqUsd": "500", "frozenBal": "0"},
            ],
        }
    ],
}

BYBIT_WALLET = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "list": [
            {
                "accountType": "UNIFIED",
                "coin": [
                    {"coin": "SOL", "walletBalance": "10", "usdValue": "1500", "locked": "0"},
                    {"coin": "USDC", "walletBalance": "800", "usdValue": "800", "locked": "0"},
                ],
            }
        ]
    },
}

BYBIT_QUERY_API = {
    "retCode": 0,
    "result": {"apiKey": "bybit-key", "readOnly": 1, "permissions": {"ContractTrade": [], "Spot": [], "Wallet": []}, "ips": ["*"]},
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def json(self):
        return self.payload


@pytest.fixture()
def cex_settings(monkeypatch):
    settings = Settings(portfolio_token_encryption_key=FERNET_KEY)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    monkeypatch.setattr(cex_connection_service, "get_settings", lambda: settings)
    return settings


@pytest.fixture()
def cex_http(monkeypatch):
    """Recorded venue transport. okx can be broken per-test via state."""
    state = {"okx_broken": False, "binance_rejects": False}

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/v3/account"):
            if state["binance_rejects"]:
                return FakeResponse({"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}, status_code=401)
            return FakeResponse(BINANCE_ACCOUNT)
        if url.endswith("/api/v3/ticker/price"):
            prices = {"BTCUSDT": "60000.00", "SHIBUSDT": "0.00001"}
            symbol = (params or {}).get("symbol")
            if symbol in prices:
                return FakeResponse({"symbol": symbol, "price": prices[symbol]})
            return FakeResponse({"code": -1121, "msg": "Invalid symbol."}, status_code=400)
        if url.endswith("/api/v5/account/balance"):
            if state["okx_broken"]:
                return FakeResponse({"code": "50001", "msg": "Service unavailable", "data": []}, status_code=500)
            return FakeResponse(OKX_BALANCE)
        if "/v5/user/query-api" in url:
            return FakeResponse(BYBIT_QUERY_API)
        if "/v5/account/wallet-balance" in url:
            return FakeResponse(BYBIT_WALLET)
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("packages.data.cex_private.base.requests.get", fake_get)
    return state


def _snapshots(db, account):
    return db.query(AccountSnapshot).filter_by(account_id=account.id).order_by(AccountSnapshot.captured_at.asc()).all()


# ---------------------------------------------------------------------------
# Connect → sync → NAV → brief
# ---------------------------------------------------------------------------


def test_connect_binance_creates_connection_snapshot_positions_and_brief(db, pro_user, cex_settings, cex_http):
    account = connect_cex(db, pro_user, "binance", "binance-key", "binance-secret")

    assert account.venue == "BINANCE"
    assert account.account_type == "READ_ONLY"
    assert account.base_currency == "USD"
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    assert connection.adapter == "binance"
    assert connection.status == "CONNECTED"
    assert connection.environment == "production"
    # Credentials are stored only as Fernet ciphertext and decrypt round-trip.
    assert connection.credential_ciphertext
    assert "binance-secret" not in connection.credential_ciphertext
    stored = json.loads(portfolio_service.decrypt_token(connection.credential_ciphertext))
    assert stored == {"api_key": "binance-key", "api_secret": "binance-secret", "passphrase": None}
    # Permission metadata is recorded without secrets.
    assert connection.metadata_json["permission_check"]["can_trade"] is False
    assert connection.metadata_json["permission_check"]["permissions_verified"] is True
    assert "binance-secret" not in json.dumps(connection.metadata_json)

    snapshots = _snapshots(db, account)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.equity == pytest.approx(37200.0)  # 0.6 BTC * 60000 + 1200 USDT
    assert snapshot.available_margin == pytest.approx(1200.0)
    payload = snapshot.raw_event_reference["payload"]
    assert payload["holding_count"] == 2  # SHIB dust ($0.09) filtered out
    assert payload["priced_coverage"] == 1.0
    assert payload["top1_weight"] == pytest.approx(36000.0 / 37200.0, rel=1e-4)
    assert payload["hhi"] > 0.9

    positions = db.query(PositionSnapshot).filter_by(account_id=account.id, captured_at=snapshot.captured_at).all()
    assert {row.instrument for row in positions} == {"BTC", "USDT"}

    # Idempotent re-sync: new snapshot per run, no duplicated positions.
    portfolio_service.sync_account(db, pro_user, account)
    snapshots = _snapshots(db, account)
    assert len(snapshots) == 2
    latest = snapshots[-1]
    assert latest.daily_pnl == pytest.approx(0.0)  # 24h change vs previous snapshot
    assert db.query(PositionSnapshot).filter_by(account_id=account.id, captured_at=latest.captured_at).count() == 2

    # First-run personalization: exactly one deterministic brief, no LLM.
    briefs = db.query(Report).filter_by(idempotency_key=f"first-portfolio-brief:{pro_user.id}:{account.id}").all()
    assert len(briefs) == 1
    assert briefs[0].report_type == "portfolio_daily"
    assert "NAV: $37,200.00" in briefs[0].content_markdown
    portfolio_service.sync_account(db, pro_user, account)
    assert db.query(Report).filter_by(idempotency_key=f"first-portfolio-brief:{pro_user.id}:{account.id}").count() == 1

    # Context includes the account with concentration metadata.
    context = portfolio_service.portfolio_context(db, pro_user.id)
    assert context["connected"] is True
    assert account.id in context["portfolio_ids"]
    assert context["total_nav"] == pytest.approx(37200.0)
    assert context["concentration_hhi"] is not None


def test_cex_connect_api_contract_never_echoes_secrets(api_client, db, pro_user, cex_settings, cex_http):
    response = api_client.post(
        "/portfolio/cex/connect",
        headers=auth_headers(pro_user),
        json={"venue": "binance", "api_key": "binance-key", "api_secret": "binance-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["next_step"] == "choose_channels"
    assert body["connected"] is True
    connection_row = next(item for item in body["connections"] if item["provider"] == "binance")
    assert connection_row["last_sync"] is not None
    assert connection_row["error"] is None
    # DB-level status is CONNECTED (the view may additionally age-flag STALE).
    assert db.query(ExchangeConnection).filter_by(user_id=pro_user.id, adapter="binance").one().status == "CONNECTED"
    serialized = json.dumps(body)
    assert "binance-secret" not in serialized
    assert "binance-key" not in serialized

    snapshot = api_client.get("/portfolio", headers=auth_headers(pro_user))
    assert snapshot.status_code == 200
    serialized = json.dumps(snapshot.json())
    assert "binance-secret" not in serialized
    assert "binance-key" not in serialized
    assert snapshot.json()["providers"]["binance"] is True


def test_invalid_credentials_return_400_and_persist_nothing(api_client, db, pro_user, cex_settings, cex_http):
    cex_http["binance_rejects"] = True
    response = api_client.post(
        "/portfolio/cex/connect",
        headers=auth_headers(pro_user),
        json={"venue": "binance", "api_key": "bad-key", "api_secret": "bad-secret"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CEX_PERMISSION_DENIED"
    assert "bad-secret" not in json.dumps(response.json())
    assert db.query(TradingAccount).filter_by(user_id=pro_user.id, venue="BINANCE").count() == 0
    assert db.query(ExchangeConnection).filter_by(user_id=pro_user.id, adapter="binance").count() == 0


def test_private_key_and_seed_phrase_material_is_rejected(db, pro_user, cex_settings, cex_http):
    with pytest.raises(ValueError, match="CEX_KEY_MATERIAL_REJECTED"):
        connect_cex(db, pro_user, "binance", "key", "0x" + "ab" * 32)
    with pytest.raises(ValueError, match="CEX_KEY_MATERIAL_REJECTED"):
        connect_cex(db, pro_user, "okx", "key", "word " * 11 + "final", "passphrase")
    assert db.query(TradingAccount).filter_by(user_id=pro_user.id).count() == 0


def test_venue_failure_is_isolated_and_other_venues_keep_working(api_client, db, max_user, cex_settings, cex_http):
    binance = connect_cex(db, max_user, "binance", "binance-key", "binance-secret")
    okx = connect_cex(db, max_user, "okx", "okx-key", "okx-secret", "okx-pass")
    assert db.query(ExchangeConnection).filter_by(account_id=okx.id).one().status == "CONNECTED"

    cex_http["okx_broken"] = True
    failed = api_client.post(f"/portfolio/accounts/{okx.id}/sync", headers=auth_headers(max_user))
    assert failed.status_code == 502
    okx_connection = db.query(ExchangeConnection).filter_by(account_id=okx.id).one()
    assert okx_connection.status == "ERROR"
    assert okx_connection.error_code == "SYNC_FAILED"

    # Binance is unaffected and still syncs through the same router.
    ok = api_client.post(f"/portfolio/accounts/{binance.id}/sync", headers=auth_headers(max_user))
    assert ok.status_code == 200
    body = ok.json()
    by_provider = {item["provider"]: item for item in body["connections"]}
    # The view surfaces the provider error while DB-level status is ERROR.
    assert by_provider["okx"]["error"]
    assert by_provider["binance"]["error"] is None
    assert db.query(ExchangeConnection).filter_by(account_id=binance.id).one().status == "CONNECTED"
    assert db.query(ExchangeConnection).filter_by(account_id=okx.id).one().status == "ERROR"
    assert body["nav"] == pytest.approx(37200.0 + 1900.0)
    assert "okx-secret" not in json.dumps(body) and "okx-pass" not in json.dumps(body)


def test_disconnect_removes_account_from_context_immediately(db, pro_user, cex_settings, cex_http):
    account = connect_cex(db, pro_user, "binance", "binance-key", "binance-secret")
    context = portfolio_service.portfolio_context(db, pro_user.id)
    assert account.id in context["portfolio_ids"]
    assert context["connected"] is True

    portfolio_service.disconnect_account(db, pro_user, account)

    # portfolio_context reads straight from the database (no cache to bust),
    # so the account disappears immediately.
    context = portfolio_service.portfolio_context(db, pro_user.id)
    assert account.id not in context["portfolio_ids"]
    assert context["connected"] is False
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    assert connection.status == "DISCONNECTED"
    assert connection.credential_ciphertext is None
    assert portfolio_service.portfolio_view(db, pro_user)["connected"] is False


def test_duplicate_connect_same_venue_updates_instead_of_duplicating(db, pro_user, cex_settings, cex_http):
    first = connect_cex(db, pro_user, "binance", "binance-key", "binance-secret")
    second = connect_cex(db, pro_user, "binance", "binance-key-2", "binance-secret-2")

    assert first.id == second.id
    assert db.query(TradingAccount).filter_by(user_id=pro_user.id, venue="BINANCE").count() == 1
    connection = db.query(ExchangeConnection).filter_by(account_id=first.id, adapter="binance").one()
    stored = json.loads(portfolio_service.decrypt_token(connection.credential_ciphertext))
    assert stored["api_key"] == "binance-key-2"
    assert stored["api_secret"] == "binance-secret-2"


def test_testnet_connect_records_environment(api_client, db, pro_user, cex_settings, cex_http):
    response = api_client.post(
        "/portfolio/cex/connect",
        headers=auth_headers(pro_user),
        json={"venue": "binance", "api_key": "binance-key", "api_secret": "binance-secret", "environment": "testnet"},
    )
    assert response.status_code == 200
    connection = db.query(ExchangeConnection).filter_by(user_id=pro_user.id, adapter="binance").one()
    assert connection.environment == "testnet"
    assert connection.metadata_json["cex_environment"] == "testnet"


def test_bybit_connect_via_router(db, max_user, cex_settings, cex_http):
    account = connect_cex(db, max_user, "bybit", "bybit-key", "bybit-secret")
    connection = db.query(ExchangeConnection).filter_by(account_id=account.id).one()
    assert connection.status == "CONNECTED"
    assert connection.metadata_json["permission_check"]["permissions_verified"] is True
    snapshot = _snapshots(db, account)[-1]
    assert snapshot.equity == pytest.approx(2300.0)
    assert snapshot.available_margin == pytest.approx(800.0)
    positions = db.query(PositionSnapshot).filter_by(account_id=account.id, captured_at=snapshot.captured_at).all()
    assert {row.instrument for row in positions} == {"SOL", "USDC"}
