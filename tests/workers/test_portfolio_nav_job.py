"""Worker tests for the general scheduled portfolio NAV refresh job (P0-7).

The NAV job must refresh every connected portfolio account regardless of
Autopilot state and must preserve an account's previous valid snapshot when a
single source fails during a run.
"""

from __future__ import annotations

from datetime import timedelta

from packages.database.models import AccountSnapshot, ExchangeConnection, TradingAccount, utcnow
from packages.workers import tasks


def _make_account(db, user, *, venue="EVM"):
    account = TradingAccount(
        user_id=user.id,
        name="Test Wallet",
        venue=venue,
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
        permissions_json={"read_positions": True},
    )
    db.add(account)
    db.flush()
    db.add(
        ExchangeConnection(
            user_id=user.id,
            account_id=account.id,
            adapter=venue.lower(),
            environment="production",
            status="CONNECTED",
            metadata_json={"wallet_address": "0x" + "1" * 40},
        )
    )
    db.commit()
    db.refresh(account)
    return account


def test_sync_all_portfolio_accounts_refreshes_connected_accounts(monkeypatch, db, pro_user):
    account = _make_account(db, pro_user)
    called = []

    def fake_sync(_db, user, acct):
        called.append((user.id, acct.id))
        _db.add(
            AccountSnapshot(
                user_id=user.id,
                account_id=acct.id,
                balance=1000.0,
                equity=1000.0,
                available_margin=0.0,
                daily_pnl=0.0,
                stale=False,
                captured_at=utcnow(),
            )
        )
        _db.commit()

    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(tasks, "sync_account", fake_sync)

    result = tasks.sync_all_portfolio_accounts.run()

    assert called == [(pro_user.id, account.id)]
    assert result["synced"] == 1
    assert result["errors"] == 0
    assert result["accounts"] == 1


def test_sync_all_portfolio_accounts_skips_fresh_snapshots(monkeypatch, db, pro_user):
    account = _make_account(db, pro_user)
    db.add(
        AccountSnapshot(
            user_id=pro_user.id,
            account_id=account.id,
            balance=1000.0,
            equity=1000.0,
            available_margin=0.0,
            daily_pnl=0.0,
            stale=False,
            captured_at=utcnow(),
        )
    )
    db.commit()
    called = []

    def fake_sync(_db, user, acct):
        called.append(acct.id)

    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(tasks, "sync_account", fake_sync)

    result = tasks.sync_all_portfolio_accounts.run()

    assert called == []
    assert result["synced"] == 0
    assert result["skipped"] == 1


def test_sync_all_portfolio_accounts_preserves_last_valid_snapshot_on_failure(monkeypatch, db, pro_user):
    account = _make_account(db, pro_user)
    previous_captured_at = utcnow() - timedelta(hours=1)
    db.add(
        AccountSnapshot(
            user_id=pro_user.id,
            account_id=account.id,
            balance=5000.0,
            equity=5000.0,
            available_margin=0.0,
            daily_pnl=0.0,
            stale=False,
            captured_at=previous_captured_at,
        )
    )
    db.commit()

    def failing_sync(_db, user, acct):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(tasks, "sync_account", failing_sync)

    result = tasks.sync_all_portfolio_accounts.run()

    assert result["errors"] == 1
    snapshot = (
        db.query(AccountSnapshot)
        .filter_by(account_id=account.id)
        .order_by(AccountSnapshot.captured_at.desc())
        .first()
    )
    assert snapshot.captured_at == previous_captured_at
    assert snapshot.equity == 5000.0  # previous valid snapshot preserved
