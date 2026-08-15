"""Immutable append-only trading ledger.

UPDATE/DELETE are rejected by SQLAlchemy events on the model. Balances are
always DERIVED by summing entries — there is no mutable balance row that could
drift. Reconciliation differences are posted as new
``reconciliation_adjustment`` entries and never rewrite history.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from packages.database.models import LedgerEntry
from packages.live_trading.enums import LedgerEntryType


class LedgerError(RuntimeError):
    pass


def post_entry(
    db: Session,
    *,
    user_id: str,
    account_id: str,
    entry_type: LedgerEntryType | str,
    amount: Decimal | float | str,
    currency: str = "USD",
    mandate_id: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    symbol: str | None = None,
    quantity: Decimal | float | str | None = None,
    price: Decimal | float | str | None = None,
    idempotency_key: str,
    trace_id: str,
) -> LedgerEntry:
    existing = (
        db.query(LedgerEntry).filter_by(idempotency_key=idempotency_key).one_or_none()
    )
    if existing:
        return existing
    amount_dec = Decimal(str(amount))
    balance_after = cash_balance(db, account_id, for_update=True) + amount_dec
    row = LedgerEntry(
        user_id=user_id,
        account_id=account_id,
        mandate_id=mandate_id,
        entry_type=str(entry_type),
        ref_type=ref_type,
        ref_id=ref_id,
        symbol=symbol.upper() if symbol else None,
        quantity=Decimal(str(quantity)) if quantity is not None else None,
        price=Decimal(str(price)) if price is not None else None,
        amount=amount_dec,
        currency=currency,
        balance_after=balance_after,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
    )
    db.add(row)
    db.flush()
    return row


def cash_balance(db: Session, account_id: str, *, for_update: bool = False) -> Decimal:
    query = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter(
        LedgerEntry.account_id == account_id
    )
    if for_update:
        query = query.with_for_update()
    return Decimal(str(query.scalar() or 0))


def position_quantities(db: Session, account_id: str) -> dict[str, Decimal]:
    """Derived positions: sum of signed quantities per symbol from trades."""
    rows = (
        db.query(
            LedgerEntry.symbol,
            func.coalesce(func.sum(LedgerEntry.quantity), 0),
        )
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.entry_type.in_(["trade_buy", "trade_sell"]),
            LedgerEntry.symbol.isnot(None),
        )
        .group_by(LedgerEntry.symbol)
        .all()
    )
    return {str(symbol).upper(): Decimal(str(qty)) for symbol, qty in rows if symbol}


def realized_pnl(db: Session, account_id: str, *, since=None) -> Decimal:
    """Realized PnL from sell entries for an account, optionally since a date."""
    query = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter(
        LedgerEntry.account_id == account_id,
        LedgerEntry.entry_type.in_(["trade_sell", "fee", "funding", "dividend"]),
    )
    if since is not None:
        query = query.filter(LedgerEntry.created_at >= since)
    return Decimal(str(query.scalar() or 0))


def daily_realized_pnl(db: Session, account_id: str) -> Decimal:
    from datetime import datetime, time, timezone

    today = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    return realized_pnl(db, account_id, since=today)


def entries_for(
    db: Session,
    account_id: str,
    *,
    limit: int = 200,
) -> list[LedgerEntry]:
    return (
        db.query(LedgerEntry)
        .filter_by(account_id=account_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
