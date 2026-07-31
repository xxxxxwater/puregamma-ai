from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.api.routers import custody as custody_router
from apps.api.services import custody_service
from apps.api.services.runtime_sync_service import sync_runtime_account
from packages.database.models import (
    CustodyLedgerEntry,
    CustodySubAccount,
    ExchangeConnection,
    OrderJournal,
    TradingAccount,
)
from tests.conftest import auth_headers

BTC_TESTNET_ADDRESS = "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"


def _unconfigured_settings():
    return SimpleNamespace(
        app_environment="development",
        custody_provider_api_key="",
        custody_provider_api_secret="",
    )


@pytest.fixture(autouse=True)
def no_provider_credentials(monkeypatch):
    monkeypatch.setattr(
        custody_service,
        "get_settings",
        lambda: SimpleNamespace(
            custody_provider_api_key="", custody_provider_api_secret=""
        ),
    )


def _deposit(api_client, user, asset: str, amount: str, tx_ref: str) -> dict:
    response = api_client.post(
        "/custody/deposits/confirm",
        json={"asset": asset, "amount": amount, "tx_ref": tx_ref},
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    return response.json()["deposit"]


def _balances(api_client, user) -> dict[str, dict]:
    response = api_client.get("/custody/balances", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return {row["asset"]: row for row in response.json()["balances"]}


# ---------------------------------------------------------------- auth


def test_auth_required(api_client):
    assert api_client.get("/custody/account").status_code == 401
    assert api_client.get("/custody/balances").status_code == 401
    assert api_client.get("/custody/ledger").status_code == 401
    assert api_client.get("/custody/withdrawals").status_code == 401
    assert (
        api_client.post(
            "/custody/deposits/confirm",
            json={"asset": "USD", "amount": "1", "tx_ref": "tx-unauth"},
        ).status_code
        == 401
    )


# ---------------------------------------------------------------- account


def test_account_unconfigured_never_claims_custody(api_client, normal_user):
    response = api_client.get("/custody/account", headers=auth_headers(normal_user))
    assert response.status_code == 200, response.text
    account = response.json()["account"]
    assert account["status"] == "UNCONFIGURED"
    assert account["deposit_address"] is None  # never a fake address
    assert account["provider_configured"] is False
    assert account["environment"] == "testnet"
    # Explicit unavailable labeling; no "custodied"/"filled" wording anywhere.
    assert account["label"] == "unavailable-unconfigured"
    payload = response.text.lower()
    assert "custodied" not in payload
    assert "filled" not in payload


# ---------------------------------------------------------------- deposits


def test_deposit_confirm_testnet_idempotent(api_client, normal_user):
    deposit = _deposit(api_client, normal_user, "USD", "100.5", "tx-dep-1")
    assert deposit["status"] == "credited"
    assert Decimal(deposit["amount"]) == Decimal("100.5")

    duplicate = _deposit(api_client, normal_user, "USD", "100.5", "tx-dep-1")
    assert duplicate["id"] == deposit["id"]

    balances = _balances(api_client, normal_user)
    assert Decimal(balances["USD"]["available"]) == Decimal("100.5")  # credited once
    assert Decimal(balances["USD"]["frozen"]) == Decimal("0")


def test_deposit_confirm_forbidden_in_production(api_client, normal_user, monkeypatch):
    fake = SimpleNamespace(
        app_environment="production",
        custody_provider_api_key="",
        custody_provider_api_secret="",
    )
    monkeypatch.setattr(custody_router, "get_settings", lambda: fake)
    response = api_client.post(
        "/custody/deposits/confirm",
        json={"asset": "USD", "amount": "10", "tx_ref": "tx-prod-1"},
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CUSTODY_LIVE_DISABLED"
    detail = response.json()["detail"]
    assert detail["message_en"] and detail["message_zh"]


def test_balances_view_shape(api_client, normal_user):
    _deposit(api_client, normal_user, "USD", "42", "tx-shape-1")
    response = api_client.get("/custody/balances", headers=auth_headers(normal_user))
    assert response.status_code == 200
    rows = response.json()["balances"]
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {"sub_account_id", "asset", "available", "frozen", "account"}
    assert row["asset"] == "USD"
    assert isinstance(row["available"], str) and isinstance(row["frozen"], str)
    assert set(row["account"]) == {"id", "venue", "environment", "status"}
    assert row["account"]["status"] == "UNCONFIGURED"
    # No secrets and no custodied/filled wording.
    payload = response.text.lower()
    assert "credential" not in payload and "custodied" not in payload


# ---------------------------------------------------------------- ledger


def test_ledger_endpoint_with_asset_filter(api_client, normal_user):
    _deposit(api_client, normal_user, "USD", "10", "tx-led-1")
    _deposit(api_client, normal_user, "USD", "5", "tx-led-2")
    _deposit(api_client, normal_user, "BTC", "1", "tx-led-3")

    response = api_client.get(
        "/custody/ledger", params={"asset": "USD"}, headers=auth_headers(normal_user)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    entry = body["items"][0]
    assert entry["entry_type"] == "deposit_confirm"
    assert entry["asset"] == "USD"
    assert isinstance(entry["amount"], str)
    assert isinstance(entry["available_after"], str)
    assert isinstance(entry["frozen_after"], str)
    assert entry["idempotency_key"]

    empty = api_client.get(
        "/custody/ledger", params={"asset": "ETH"}, headers=auth_headers(normal_user)
    )
    assert empty.json()["total"] == 0
    everything = api_client.get("/custody/ledger", headers=auth_headers(normal_user))
    assert everything.json()["total"] == 3


# ---------------------------------------------------------------- withdrawals


def test_withdrawal_flow_cancel_releases_hold(api_client, normal_user):
    _deposit(api_client, normal_user, "BTC", "2", "tx-wd-1")
    created = api_client.post(
        "/custody/withdrawals",
        json={
            "asset": "BTC",
            "amount": "1.5",
            "address": BTC_TESTNET_ADDRESS,
            "idempotency_key": "wd-api-key-1",
        },
        headers=auth_headers(normal_user),
    )
    assert created.status_code == 200, created.text
    withdrawal = created.json()["withdrawal"]
    assert withdrawal["status"] == "intent"
    assert withdrawal["address"] == BTC_TESTNET_ADDRESS

    balances = _balances(api_client, normal_user)
    assert Decimal(balances["BTC"]["available"]) == Decimal("0.5")
    assert Decimal(balances["BTC"]["frozen"]) == Decimal("1.5")

    # Same idempotency key returns the same withdrawal (no second hold).
    duplicate = api_client.post(
        "/custody/withdrawals",
        json={
            "asset": "BTC",
            "amount": "1.5",
            "address": BTC_TESTNET_ADDRESS,
            "idempotency_key": "wd-api-key-1",
        },
        headers=auth_headers(normal_user),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["withdrawal"]["id"] == withdrawal["id"]

    listed = api_client.get("/custody/withdrawals", headers=auth_headers(normal_user))
    assert listed.json()["total"] == 1

    cancelled = api_client.post(
        f"/custody/withdrawals/{withdrawal['id']}/cancel", headers=auth_headers(normal_user)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["withdrawal"]["status"] == "rejected"
    assert cancelled.json()["withdrawal"]["error"] == "USER_CANCELLED"

    balances = _balances(api_client, normal_user)
    assert Decimal(balances["BTC"]["available"]) == Decimal("2")
    assert Decimal(balances["BTC"]["frozen"]) == Decimal("0")

    # Terminal withdrawals cannot be cancelled again.
    again = api_client.post(
        f"/custody/withdrawals/{withdrawal['id']}/cancel", headers=auth_headers(normal_user)
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "WITHDRAWAL_NOT_CANCELLABLE"

    ledger = api_client.get(
        "/custody/ledger", params={"asset": "BTC"}, headers=auth_headers(normal_user)
    )
    entry_types = [item["entry_type"] for item in ledger.json()["items"]]
    assert entry_types.count("withdrawal_hold") == 1
    assert entry_types.count("withdrawal_release") == 1


def test_withdrawal_validation_errors(api_client, normal_user):
    _deposit(api_client, normal_user, "BTC", "1", "tx-wd-err")
    bad_address = api_client.post(
        "/custody/withdrawals",
        json={
            "asset": "BTC",
            "amount": "0.1",
            "address": "definitely-not-an-address",
            "idempotency_key": "wd-bad-key-1",
        },
        headers=auth_headers(normal_user),
    )
    assert bad_address.status_code == 400
    assert bad_address.json()["detail"]["code"] == "INVALID_ADDRESS"

    too_much = api_client.post(
        "/custody/withdrawals",
        json={
            "asset": "BTC",
            "amount": "10",
            "address": BTC_TESTNET_ADDRESS,
            "idempotency_key": "wd-bad-key-2",
        },
        headers=auth_headers(normal_user),
    )
    assert too_much.status_code == 400
    assert too_much.json()["detail"]["code"] == "INSUFFICIENT_CUSTODY_BALANCE"


def test_withdrawals_are_tenant_scoped(api_client, normal_user, user_factory):
    other = user_factory("custody-other@puregamma.ai")
    _deposit(api_client, normal_user, "BTC", "1", "tx-tenant-1")
    created = api_client.post(
        "/custody/withdrawals",
        json={
            "asset": "BTC",
            "amount": "0.5",
            "address": BTC_TESTNET_ADDRESS,
            "idempotency_key": "wd-tenant-1",
        },
        headers=auth_headers(normal_user),
    )
    withdrawal_id = created.json()["withdrawal"]["id"]
    assert api_client.get("/custody/withdrawals", headers=auth_headers(other)).json()["total"] == 0
    not_found = api_client.post(
        f"/custody/withdrawals/{withdrawal_id}/cancel", headers=auth_headers(other)
    )
    assert not_found.status_code == 404
    assert api_client.get("/custody/balances", headers=auth_headers(other)).json()["balances"] == []


# ---------------------------------------------------------------- reconcile


def test_reconcile_is_admin_only(api_client, normal_user, admin_user):
    forbidden = api_client.post(
        "/custody/reconcile", json={"asset": "USD"}, headers=auth_headers(normal_user)
    )
    assert forbidden.status_code == 403

    unavailable = api_client.post(
        "/custody/reconcile", json={"asset": "USD"}, headers=auth_headers(admin_user)
    )
    assert unavailable.status_code == 200, unavailable.text
    assert unavailable.json()["reconciliation"]["status"] == "UNAVAILABLE"
    assert unavailable.json()["reconciliation"]["external_balance"] is None

    _deposit(api_client, normal_user, "USD", "25", "tx-rec-1")
    matched = api_client.post(
        "/custody/reconcile",
        json={"asset": "USD", "external_balance": "25"},
        headers=auth_headers(admin_user),
    )
    assert matched.json()["reconciliation"]["status"] == "MATCH"
    assert Decimal(matched.json()["reconciliation"]["difference"]) == Decimal("0")

    mismatched = api_client.post(
        "/custody/reconcile",
        json={"asset": "USD", "external_balance": "20"},
        headers=auth_headers(admin_user),
    )
    assert mismatched.json()["reconciliation"]["status"] == "MISMATCH"
    assert Decimal(mismatched.json()["reconciliation"]["difference"]) == Decimal("-5")


# ---------------------------------------------------------------- execution wiring


class FakeFillRuntime:
    """NautilusRuntimeClient stand-in returning one BUY fill and one SELL fill."""

    def account_state(self, account_id: str) -> dict:
        return {
            "account": {
                "balance": 1000.0,
                "equity": 1000.0,
                "available_margin": 1000.0,
                "daily_pnl": 0.0,
                "drawdown": 0.0,
                "exposure": 0.0,
                "stale": False,
            },
            "positions": [],
            "orders": [
                {
                    "client_order_id": "c-buy-1",
                    "sequence": 1,
                    "instrument": "BTCUSDT",
                    "venue": "MOCK",
                    "side": "BUY",
                    "state": "FILLED",
                    "quantity": 0.01,
                    "notional": 600.0,
                    "filled_quantity": 0.01,
                    "remaining_quantity": 0.0,
                    "average_price": 60000.0,
                },
                {
                    "client_order_id": "c-sell-1",
                    "sequence": 1,
                    "instrument": "BTCUSDT",
                    "venue": "MOCK",
                    "side": "SELL",
                    "state": "FILLED",
                    "quantity": 0.005,
                    "notional": 300.0,
                    "filled_quantity": 0.005,
                    "remaining_quantity": 0.0,
                    "average_price": 60000.0,
                },
            ],
        }

    def events(self, limit: int = 500) -> dict:
        return {"events": []}


def _custody_linked_account(db, user):
    custody_account = custody_service.get_or_create_custody_account(db)
    trading = TradingAccount(
        user_id=user.id,
        name="Paper",
        venue="MOCK",
        account_type="PAPER",
        status="ACTIVE",
    )
    db.add(trading)
    db.flush()
    db.add(
        ExchangeConnection(
            user_id=user.id,
            account_id=trading.id,
            adapter="mock",
            environment="paper",
            status="CONNECTED",
            metadata_json={"custody_account_id": custody_account.id},
        )
    )
    db.commit()
    return trading, custody_account


def test_sync_fill_settles_into_custody(db, normal_user):
    trading, custody_account = _custody_linked_account(db, normal_user)
    sub = custody_service.ensure_sub_account(db, custody_account, normal_user.id, "USD")
    custody_service.credit_deposit(db, sub, Decimal("1000"), tx_ref="t", external_ref="e")
    db.commit()

    result = sync_runtime_account(db, trading, runtime=FakeFillRuntime())
    assert result["orders"] == 2

    entries = (
        db.query(CustodyLedgerEntry)
        .filter_by(sub_account_id=sub.id)
        .order_by(CustodyLedgerEntry.created_at.asc(), CustodyLedgerEntry.id.asc())
        .all()
    )
    by_type = {}
    for entry in entries:
        by_type.setdefault(entry.entry_type, []).append(entry)
    # BUY: freeze 600 then debit the frozen hold; SELL: credit 300 proceeds.
    assert [Decimal(str(e.amount)) for e in by_type["freeze"]] == [Decimal("600")]
    assert [Decimal(str(e.amount)) for e in by_type["trade_debit"]] == [Decimal("600")]
    assert [Decimal(str(e.amount)) for e in by_type["trade_credit"]] == [Decimal("300")]
    assert by_type["freeze"][0].idempotency_key == "custody:freeze:c-buy-1"
    assert by_type["trade_debit"][0].idempotency_key == "custody:debit:c-buy-1:1"
    assert by_type["trade_credit"][0].idempotency_key == "custody:credit:c-sell-1:1"

    db.refresh(sub)
    assert Decimal(str(sub.available)) == Decimal("700")
    assert Decimal(str(sub.frozen)) == Decimal("0")

    journals = db.query(OrderJournal).filter_by(account_id=trading.id).all()
    assert all(journal.error_code is None for journal in journals)

    # Re-running the sync is fully idempotent: no duplicate journals or entries.
    sync_runtime_account(db, trading, runtime=FakeFillRuntime())
    assert db.query(CustodyLedgerEntry).filter_by(sub_account_id=sub.id).count() == len(entries)
    db.refresh(sub)
    assert Decimal(str(sub.available)) == Decimal("700")


def test_sync_fill_without_custody_link_is_unchanged(db, normal_user):
    trading = TradingAccount(
        user_id=normal_user.id,
        name="Unlinked",
        venue="MOCK",
        account_type="PAPER",
        status="ACTIVE",
    )
    db.add(trading)
    db.commit()

    result = sync_runtime_account(db, trading, runtime=FakeFillRuntime())
    assert result["orders"] == 2
    assert db.query(CustodyLedgerEntry).count() == 0
    assert db.query(CustodySubAccount).filter_by(user_id=normal_user.id).count() == 0
    assert db.query(OrderJournal).filter_by(account_id=trading.id).count() == 2


def test_sync_buy_fill_with_insufficient_custody_is_annotated(db, normal_user):
    trading, _ = _custody_linked_account(db, normal_user)
    # No deposit: the BUY freeze cannot be covered.
    result = sync_runtime_account(db, trading, runtime=FakeFillRuntime())
    assert result["orders"] == 2
    buy = db.query(OrderJournal).filter_by(client_order_id="c-buy-1").one()
    assert buy.error_code == "CUSTODY_INSUFFICIENT_BALANCE"
    # The SELL leg still credited proceeds honestly; no balances were invented.
    sell = db.query(OrderJournal).filter_by(client_order_id="c-sell-1").one()
    assert sell.error_code is None
    sub = (
        db.query(CustodySubAccount)
        .filter_by(user_id=normal_user.id, asset="USD")
        .one()
    )
    assert Decimal(str(sub.available)) == Decimal("300")
    assert Decimal(str(sub.frozen)) == Decimal("0")


# ------------------------------------------------------- manual order wiring


class FakeSubmitRuntime:
    """Runtime stand-in for manual order submission: immediate full fill."""

    def __init__(self):
        self.commands = []

    def command(self, command_type, idempotency_key, payload):
        self.commands.append((command_type, idempotency_key))
        return {
            "state": "FILLED",
            "sequence": 1,
            "exchange_order_id": "ex-manual-1",
            "filled_quantity": payload["quantity"],
            "remaining_quantity": 0.0,
            "average_price": 60000.0,
        }


def _preview_and_confirm(db, user, trading, runtime, *, notional=600.0, quantity=0.01):
    from apps.api.services.trading_service import confirm_order, preview_order

    intent, token = preview_order(
        db,
        user.id,
        {
            "account_id": trading.id,
            "instrument": "BTCUSDT",
            "venue": "MOCK",
            "direction": "BUY",
            "quantity": quantity,
            "notional": notional,
            "order_type": "MARKET",
            "execution_mode": "PAPER",
            "idempotency_key": f"manual-{trading.id}-{notional}",
        },
    )
    return confirm_order(db, user.id, intent.id, token, runtime=runtime), intent


def test_manual_order_fill_freezes_then_debits_custody(db, max_user):
    trading, custody_account = _custody_linked_account(db, max_user)
    sub = custody_service.ensure_sub_account(db, custody_account, max_user.id, "USD")
    custody_service.credit_deposit(db, sub, Decimal("1000"), tx_ref="t", external_ref="e")
    db.commit()

    journal, intent = _preview_and_confirm(db, max_user, trading, FakeSubmitRuntime())
    assert journal.state == "FILLED"

    entries = {
        entry.idempotency_key: entry
        for entry in db.query(CustodyLedgerEntry).filter_by(sub_account_id=sub.id).all()
    }
    assert f"custody:freeze:{intent.id}" in entries
    assert f"custody:debit:{journal.id}" in entries
    assert Decimal(str(entries[f"custody:freeze:{intent.id}"].amount)) == Decimal("600")
    assert Decimal(str(entries[f"custody:debit:{journal.id}"].amount)) == Decimal("600")
    db.refresh(sub)
    assert Decimal(str(sub.available)) == Decimal("400")
    assert Decimal(str(sub.frozen)) == Decimal("0")


def test_manual_order_blocked_before_runtime_when_custody_insufficient(db, max_user):
    from apps.api.services.trading_service import TradingServiceError

    trading, _ = _custody_linked_account(db, max_user)
    runtime = FakeSubmitRuntime()  # no deposit at all
    with pytest.raises(TradingServiceError, match="Insufficient custody balance"):
        _preview_and_confirm(db, max_user, trading, runtime)
    # The hold guard fired before the order ever reached the runtime.
    assert runtime.commands == []
