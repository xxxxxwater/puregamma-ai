from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.api.services import custody_service
from apps.api.services.custody_service import (
    InsufficientCustodyBalance,
    InvalidWithdrawalAddress,
    InvalidWithdrawalTransition,
    UnsupportedWithdrawalAsset,
)
from packages.database.models import (
    CustodyDeposit,
    CustodyLedgerEntry,
    CustodyReconciliation,
    CustodyWithdrawal,
)

BTC_TESTNET_ADDRESS = "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"
ETH_ADDRESS = "0x" + "a" * 40


@pytest.fixture(autouse=True)
def no_provider_credentials(monkeypatch):
    """Deterministic credential state regardless of ambient env."""
    monkeypatch.setattr(
        custody_service,
        "get_settings",
        lambda: SimpleNamespace(
            custody_provider_api_key="", custody_provider_api_secret=""
        ),
    )


def _account(db, **kwargs):
    return custody_service.get_or_create_custody_account(db, **kwargs)


def _sub(db, account, user_id, asset="USD"):
    return custody_service.ensure_sub_account(db, account, user_id, asset)


def _entries(db, sub_account_id):
    return (
        db.query(CustodyLedgerEntry)
        .filter_by(sub_account_id=sub_account_id)
        .order_by(CustodyLedgerEntry.created_at.asc(), CustodyLedgerEntry.id.asc())
        .all()
    )


def test_account_is_unconfigured_without_credentials_no_fake_address(db):
    account = _account(db)
    assert account.status == "UNCONFIGURED"
    assert account.deposit_address is None  # never a fabricated address
    assert custody_service.provider_credentials_configured() is False
    # Singleton per (venue, environment)
    again = _account(db)
    assert again.id == account.id


def test_account_active_with_credentials_but_no_invented_address(db, monkeypatch):
    monkeypatch.setattr(
        custody_service,
        "get_settings",
        lambda: SimpleNamespace(
            custody_provider_api_key="k", custody_provider_api_secret="s"
        ),
    )
    account = _account(db, venue="anchorage", environment="sandbox")
    assert account.status == "ACTIVE"
    assert account.deposit_address is None  # only the provider may supply it


def test_deposit_credit_is_idempotent_on_external_ref(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "USD")
    deposit = custody_service.credit_deposit(
        db, sub, Decimal("100.5"), tx_ref="tx-1", external_ref="ext-1"
    )
    duplicate = custody_service.credit_deposit(
        db, sub, Decimal("100.5"), tx_ref="tx-1", external_ref="ext-1"
    )
    assert duplicate.id == deposit.id
    assert deposit.status == "credited"
    assert Decimal(str(sub.available)) == Decimal("100.5")
    assert Decimal(str(sub.frozen)) == Decimal("0")
    assert db.query(CustodyDeposit).count() == 1
    entries = _entries(db, sub.id)
    assert len(entries) == 1
    assert entries[0].entry_type == "deposit_confirm"
    assert Decimal(str(entries[0].available_after)) == Decimal("100.5")


def test_freeze_debit_credit_round_trip_decimal_exactness(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "USD")
    custody_service.credit_deposit(
        db, sub, Decimal("1000.25"), tx_ref="tx-rt", external_ref="ext-rt"
    )

    freeze_entry = custody_service.freeze(
        db, sub, Decimal("400.125"), ("order", "ord-1"), idempotency_key="k-freeze-1"
    )
    assert Decimal(str(sub.available)) == Decimal("600.125")
    assert Decimal(str(sub.frozen)) == Decimal("400.125")
    assert Decimal(str(freeze_entry.available_after)) == Decimal("600.125")
    assert Decimal(str(freeze_entry.frozen_after)) == Decimal("400.125")

    debit_entry = custody_service.trade_debit(
        db, sub, Decimal("150.0625"), ("fill", "fill-1"), idempotency_key="k-debit-1"
    )
    assert Decimal(str(sub.frozen)) == Decimal("250.0625")
    assert Decimal(str(debit_entry.frozen_after)) == Decimal("250.0625")
    assert Decimal(str(debit_entry.available_after)) == Decimal("600.125")

    credit_entry = custody_service.trade_credit(
        db, sub, Decimal("175.5"), ("fill", "fill-2"), idempotency_key="k-credit-1"
    )
    assert Decimal(str(sub.available)) == Decimal("775.625")
    assert Decimal(str(credit_entry.available_after)) == Decimal("775.625")

    custody_service.unfreeze(
        db, sub, Decimal("250.0625"), ("order", "ord-1"), idempotency_key="k-unfreeze-1"
    )
    assert Decimal(str(sub.available)) == Decimal("1025.6875")
    assert Decimal(str(sub.frozen)) == Decimal("0")

    # Every op is idempotent: replaying each key appends nothing and changes nothing.
    for key in ("k-freeze-1", "k-debit-1", "k-credit-1", "k-unfreeze-1"):
        existing = db.query(CustodyLedgerEntry).filter_by(idempotency_key=key).one()
        assert existing is not None
    custody_service.freeze(
        db, sub, Decimal("400.125"), ("order", "ord-1"), idempotency_key="k-freeze-1"
    )
    assert Decimal(str(sub.available)) == Decimal("1025.6875")
    assert len(_entries(db, sub.id)) == 5  # deposit + 4 ops


def test_insufficient_balance_guards(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "USD")
    with pytest.raises(InsufficientCustodyBalance):
        custody_service.freeze(db, sub, Decimal("1"), None, idempotency_key="k-f-0")
    custody_service.credit_deposit(db, sub, Decimal("10"), tx_ref="t", external_ref="e")
    with pytest.raises(InsufficientCustodyBalance):
        custody_service.freeze(db, sub, Decimal("11"), None, idempotency_key="k-f-1")
    custody_service.freeze(db, sub, Decimal("10"), None, idempotency_key="k-f-2")
    with pytest.raises(InsufficientCustodyBalance):
        custody_service.trade_debit(db, sub, Decimal("11"), None, idempotency_key="k-d-1")
    with pytest.raises(InsufficientCustodyBalance):
        custody_service.unfreeze(db, sub, Decimal("11"), None, idempotency_key="k-u-1")
    with pytest.raises(ValueError):
        custody_service.trade_credit(db, sub, Decimal("0"), None, idempotency_key="k-c-0")


def test_ledger_is_append_only(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "USD")
    custody_service.credit_deposit(db, sub, Decimal("5"), tx_ref="t", external_ref="e")
    db.commit()
    entry = _entries(db, sub.id)[0]

    entry.amount = Decimal("999")
    with pytest.raises(RuntimeError, match="append-only"):
        db.flush()
    db.rollback()

    entry = _entries(db, sub.id)[0]
    db.delete(entry)
    with pytest.raises(RuntimeError, match="append-only"):
        db.flush()
    db.rollback()
    assert len(_entries(db, sub.id)) == 1


def test_withdrawal_full_lifecycle(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "BTC")
    custody_service.credit_deposit(db, sub, Decimal("2"), tx_ref="t", external_ref="e")

    withdrawal = custody_service.request_withdrawal(
        db, sub, "BTC", Decimal("1.5"), BTC_TESTNET_ADDRESS, "wd-key-1"
    )
    assert withdrawal.status == "intent"
    assert Decimal(str(sub.available)) == Decimal("0.5")
    assert Decimal(str(sub.frozen)) == Decimal("1.5")

    # Duplicate idempotency key returns the same row without a second hold.
    duplicate = custody_service.request_withdrawal(
        db, sub, "BTC", Decimal("1.5"), BTC_TESTNET_ADDRESS, "wd-key-1"
    )
    assert duplicate.id == withdrawal.id
    assert db.query(CustodyWithdrawal).count() == 1
    assert Decimal(str(sub.frozen)) == Decimal("1.5")

    # Illegal transitions are rejected.
    with pytest.raises(InvalidWithdrawalTransition):
        custody_service.mark_withdrawal_status(db, withdrawal, "confirmed")
    with pytest.raises(InvalidWithdrawalTransition):
        custody_service.mark_withdrawal_status(db, withdrawal, "submitted")

    custody_service.mark_withdrawal_status(db, withdrawal, "approved")
    assert withdrawal.status == "approved"
    custody_service.mark_withdrawal_status(db, withdrawal, "submitted", tx_ref="tx-wd-1")
    custody_service.mark_withdrawal_status(db, withdrawal, "confirmed", tx_ref="tx-wd-1")
    assert withdrawal.status == "confirmed"
    # Confirmed: funds left custody — frozen hold debited, available untouched.
    assert Decimal(str(sub.frozen)) == Decimal("0")
    assert Decimal(str(sub.available)) == Decimal("0.5")
    # Terminal: no further transitions.
    with pytest.raises(InvalidWithdrawalTransition):
        custody_service.mark_withdrawal_status(db, withdrawal, "failed")
    # Repeating the current status is a no-op replay.
    custody_service.mark_withdrawal_status(db, withdrawal, "confirmed")

    entry_types = [row.entry_type for row in _entries(db, sub.id)]
    assert entry_types == ["deposit_confirm", "withdrawal_hold", "trade_debit"]


def test_withdrawal_failure_and_cancel_release_hold(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "BTC")
    custody_service.credit_deposit(db, sub, Decimal("1"), tx_ref="t", external_ref="e")

    failed = custody_service.request_withdrawal(
        db, sub, "BTC", Decimal("0.25"), BTC_TESTNET_ADDRESS, "wd-fail-1"
    )
    custody_service.mark_withdrawal_status(db, failed, "approved")
    custody_service.mark_withdrawal_status(db, failed, "submitted")
    custody_service.mark_withdrawal_status(db, failed, "failed", error="VENUE_REJECTED")
    assert failed.status == "failed"
    assert Decimal(str(sub.available)) == Decimal("1")
    assert Decimal(str(sub.frozen)) == Decimal("0")

    cancelled = custody_service.request_withdrawal(
        db, sub, "BTC", Decimal("0.5"), BTC_TESTNET_ADDRESS, "wd-cancel-1"
    )
    custody_service.mark_withdrawal_status(db, cancelled, "rejected", error="USER_CANCELLED")
    assert cancelled.status == "rejected"
    assert Decimal(str(sub.available)) == Decimal("1")
    assert Decimal(str(sub.frozen)) == Decimal("0")

    entry_types = [row.entry_type for row in _entries(db, sub.id)]
    assert entry_types.count("withdrawal_hold") == 2
    assert entry_types.count("withdrawal_release") == 2


def test_withdrawal_address_validation(db, normal_user):
    account = _account(db)
    sub_btc = _sub(db, account, normal_user.id, "BTC")
    custody_service.credit_deposit(db, sub_btc, Decimal("1"), tx_ref="t", external_ref="e")
    with pytest.raises(InvalidWithdrawalAddress):
        custody_service.request_withdrawal(
            db, sub_btc, "BTC", Decimal("0.1"), "not-an-address", "wd-bad-1"
        )
    # ERC20-family assets use 0x addresses.
    sub_usdt = _sub(db, account, normal_user.id, "USDT")
    custody_service.credit_deposit(db, sub_usdt, Decimal("10"), tx_ref="t2", external_ref="e2")
    withdrawal = custody_service.request_withdrawal(
        db, sub_usdt, "USDT", Decimal("1"), ETH_ADDRESS, "wd-eth-1"
    )
    assert withdrawal.status == "intent"
    with pytest.raises(InvalidWithdrawalAddress):
        custody_service.request_withdrawal(
            db, sub_usdt, "USDT", Decimal("1"), BTC_TESTNET_ADDRESS, "wd-bad-2"
        )
    # Assets without a supported address schema are rejected honestly.
    sub_usd = _sub(db, account, normal_user.id, "USD")
    with pytest.raises(UnsupportedWithdrawalAsset):
        custody_service.request_withdrawal(
            db, sub_usd, "USD", Decimal("1"), ETH_ADDRESS, "wd-bad-3"
        )


def test_reconcile_match_mismatch_unavailable(db, user_factory):
    account = _account(db)
    user_a = user_factory("custody-a@puregamma.ai")
    user_b = user_factory("custody-b@puregamma.ai")
    sub_a = _sub(db, account, user_a.id, "USD")
    sub_b = _sub(db, account, user_b.id, "USD")
    custody_service.credit_deposit(db, sub_a, Decimal("100"), tx_ref="t1", external_ref="e1")
    custody_service.freeze(db, sub_a, Decimal("20"), None, idempotency_key="k-f-a")
    custody_service.credit_deposit(db, sub_b, Decimal("50"), tx_ref="t2", external_ref="e2")

    match = custody_service.reconcile(db, account, "USD", Decimal("150"))
    assert match.status == "MATCH"
    assert Decimal(str(match.difference)) == Decimal("0")
    assert Decimal(str(match.local_available)) == Decimal("130")
    assert Decimal(str(match.local_frozen)) == Decimal("20")

    mismatch = custody_service.reconcile(db, account, "USD", Decimal("149.5"))
    assert mismatch.status == "MISMATCH"
    assert Decimal(str(mismatch.difference)) == Decimal("-0.5")

    unavailable = custody_service.reconcile(db, account, "USD", None)
    assert unavailable.status == "UNAVAILABLE"
    assert unavailable.external_balance is None
    assert unavailable.difference is None

    assert db.query(CustodyReconciliation).count() == 3


def test_sub_account_view_contains_no_secrets(db, normal_user):
    account = _account(db)
    sub = _sub(db, account, normal_user.id, "USD")
    custody_service.credit_deposit(db, sub, Decimal("7"), tx_ref="t", external_ref="e")
    view = custody_service.sub_account_view(db, normal_user.id)
    assert len(view) == 1
    row = view[0]
    assert row["asset"] == "USD"
    assert row["available"] == Decimal("7")
    assert row["frozen"] == Decimal("0")
    assert row["account"]["venue"] == account.venue
    assert row["account"]["environment"] == "testnet"
    assert row["account"]["status"] == "UNCONFIGURED"
    assert "provider_ref" not in row["account"]
    other = custody_service.sub_account_view(db, "someone-else")
    assert other == []
