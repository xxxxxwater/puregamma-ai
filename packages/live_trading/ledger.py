"""Immutable append-only trading ledger.

UPDATE/DELETE are rejected by SQLAlchemy events on the model. Balances are
always DERIVED by summing entries — there is no mutable balance row that could
drift. Reconciliation differences are posted as new
``reconciliation_adjustment`` entries and never rewrite history.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, text
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
    _lock_account(db, account_id)
    # Re-check after acquiring the lock: a concurrent writer with the same
    # idempotency key may have committed while we waited.
    existing = (
        db.query(LedgerEntry).filter_by(idempotency_key=idempotency_key).one_or_none()
    )
    if existing:
        return existing
    balance_after = cash_balance(db, account_id) + amount_dec
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


def _lock_account(db: Session, account_id: str) -> None:
    """Serialize ledger writers for one account until the transaction ends.

    ``SELECT sum(...) FOR UPDATE`` is rejected by Postgres ("FOR UPDATE is not
    allowed with aggregate functions"), so balance derivation is serialized
    with a transaction-scoped advisory lock keyed on the account instead.
    SQLite (tests/dev) serializes writers at the database level, so this is a
    no-op there.
    """
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:account_id))"),
            {"account_id": str(account_id)},
        )


def cash_balance(db: Session, account_id: str, *, for_update: bool = False) -> Decimal:
    """Ledger-derived cash. ``for_update`` takes the per-account writer lock
    (aggregates cannot use row-level ``FOR UPDATE``)."""
    if for_update:
        _lock_account(db, account_id)
    query = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter(
        LedgerEntry.account_id == account_id
    )
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


_TRADE_TYPES = ("trade_buy", "trade_sell")
# Non-trade cash flows that are income/expense of trading (not transfers).
_PNL_CASH_TYPES = ("fee", "funding", "dividend")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def realized_pnl(db: Session, account_id: str, *, since: datetime | None = None) -> Decimal:
    """Realized PnL using a per-symbol signed average-cost basis.

    Trades are replayed in chronological order over the account's full
    history (so the cost basis of positions opened before ``since`` is
    known), but only gains/losses realized at or after ``since`` count.
    A trade that reduces an open position realizes
    ``(exit_price - avg_entry_price) * closed_qty`` (sign-adjusted for
    shorts); a trade with no prior position opens one at its own price and
    realizes nothing. Fees, funding and dividends since ``since`` are added
    at their signed cash amount. Deposits, withdrawals and adjustments are
    transfers, not PnL, and are excluded.
    """
    since_aware = _aware(since) if since is not None else None
    trades = (
        db.query(
            LedgerEntry.symbol,
            LedgerEntry.quantity,
            LedgerEntry.price,
            LedgerEntry.amount,
            LedgerEntry.created_at,
        )
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.entry_type.in_(_TRADE_TYPES),
            LedgerEntry.symbol.isnot(None),
        )
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
        .all()
    )
    zero = Decimal("0")
    positions: dict[str, tuple[Decimal, Decimal]] = {}  # symbol -> (qty, avg price)
    realized = zero
    for symbol, quantity, price, amount, created_at in trades:
        qty = Decimal(str(quantity)) if quantity is not None else zero
        if qty == zero:
            continue
        if price is not None and Decimal(str(price)) > zero:
            px = Decimal(str(price))
        else:
            # Derive the execution price from the cash leg when price is absent.
            px = abs(Decimal(str(amount or 0))) / abs(qty)
        key = str(symbol).upper()
        held, avg = positions.get(key, (zero, zero))
        counts = since_aware is None or (
            created_at is not None and _aware(created_at) >= since_aware
        )
        if held == zero or (held > zero) == (qty > zero):
            new_held = held + qty
            avg = ((abs(held) * avg) + (abs(qty) * px)) / abs(new_held)
            positions[key] = (new_held, avg)
            continue
        closed = min(abs(qty), abs(held))
        direction = Decimal("1") if held > zero else Decimal("-1")
        if counts:
            realized += (px - avg) * closed * direction
        new_held = held + qty
        if new_held == zero:
            positions[key] = (zero, zero)
        elif (new_held > zero) == (held > zero):
            positions[key] = (new_held, avg)
        else:
            # Position flipped: the remainder opens at this trade's price.
            positions[key] = (new_held, px)

    cash_query = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter(
        LedgerEntry.account_id == account_id,
        LedgerEntry.entry_type.in_(_PNL_CASH_TYPES),
    )
    if since is not None:
        cash_query = cash_query.filter(LedgerEntry.created_at >= since)
    realized += Decimal(str(cash_query.scalar() or 0))
    return realized


def daily_realized_pnl(db: Session, account_id: str) -> Decimal:
    """Realized PnL since UTC midnight (feeds the MAX_DAILY_LOSS check)."""
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
