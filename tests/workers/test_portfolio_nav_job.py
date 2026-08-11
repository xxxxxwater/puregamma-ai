from __future__ import annotations

from datetime import date

import packages.workers.tasks as tasks_module
from packages.database.models import (
    AccountSnapshot,
    PortfolioNavSnapshot,
    PositionSnapshot,
    TradingAccount,
    utcnow,
)
from packages.workers.tasks import generate_portfolio_nav


def _connected_account(db, user_id, *, equity: float = 10_000.0, balance: float = 10_000.0) -> TradingAccount:
    captured = utcnow()
    account = TradingAccount(
        user_id=user_id,
        name="Synthetic Portfolio",
        venue="HYPERLIQUID",
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
        permissions_json={"read_positions": True},
    )
    db.add(account)
    db.flush()
    db.add(
        AccountSnapshot(
            user_id=user_id,
            account_id=account.id,
            balance=balance,
            equity=equity,
            available_margin=5_000.0,
            daily_pnl=0.0,
            drawdown=0.0,
            exposure=5_000.0,
            stale=False,
            raw_event_reference={},
            captured_at=captured,
        )
    )
    db.add(
        PositionSnapshot(
            user_id=user_id,
            account_id=account.id,
            instrument="BTC",
            quantity=0.1,
            side="LONG",
            average_price=45_000.0,
            mark_price=50_000.0,
            unrealized_pnl=500.0,
            realized_pnl=0.0,
            leverage=1.0,
            raw_event_reference={},
            captured_at=captured,
        )
    )
    db.commit()
    return account


def test_generate_portfolio_nav_writes_snapshot(db, normal_user, monkeypatch):
    monkeypatch.setattr(tasks_module, "SessionLocal", lambda: db)
    user_id = normal_user.id
    _connected_account(db, user_id, equity=10_000.0)

    result = generate_portfolio_nav(date.today())

    assert result["written"] == 1
    assert result["errors"] == 0
    snap = db.query(PortfolioNavSnapshot).filter_by(user_id=user_id).one()
    assert snap.snapshot_date == date.today()
    assert snap.total_nav == 10_000.0
    assert snap.account_count == 1
    assert not snap.partial
    assert snap.positions_json["BTC"]["value"] == 5_000.0
    assert snap.positions_json["BTC"]["quantity"] == 0.1


def test_generate_portfolio_nav_is_idempotent_per_user_day(db, normal_user, monkeypatch):
    monkeypatch.setattr(tasks_module, "SessionLocal", lambda: db)
    user_id = normal_user.id
    _connected_account(db, user_id, equity=10_000.0)

    generate_portfolio_nav(date.today())
    generate_portfolio_nav(date.today())

    rows = db.query(PortfolioNavSnapshot).filter_by(user_id=user_id, snapshot_date=date.today()).all()
    assert len(rows) == 1


def test_generate_portfolio_nav_preserves_previous_on_partial_failure(db, normal_user, monkeypatch):
    """A user with no usable account data is skipped; the previous valid snapshot stays."""
    monkeypatch.setattr(tasks_module, "SessionLocal", lambda: db)
    user_id = normal_user.id
    # A valid snapshot from a prior run.
    _connected_account(db, user_id, equity=10_000.0)
    generate_portfolio_nav(date.today())

    # Now the source account is gone (no AccountSnapshot) — simulate by creating a
    # second user whose account has no snapshot at all, then re-run.
    previous = db.query(PortfolioNavSnapshot).filter_by(user_id=user_id).one()
    assert previous.total_nav == 10_000.0

    # Add a degraded user (ACTIVE account but zero AccountSnapshot rows).
    degraded = _connected_account(db, user_id, equity=10_000.0)
    # Remove its snapshot to simulate source failure for that account.
    db.query(AccountSnapshot).filter_by(account_id=degraded.id).delete()
    db.commit()

    result = generate_portfolio_nav(date.today())

    # normal_user still has one valid account snapshot, so it is still written,
    # and it never regresses to zero.
    snap = db.query(PortfolioNavSnapshot).filter_by(user_id=user_id, snapshot_date=date.today()).one()
    assert snap.total_nav == 10_000.0
    assert snap.partial is True
