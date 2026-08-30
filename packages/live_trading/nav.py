"""Server-side NAV calculator (MVP).

NAV = cash + Σ(position_quantity × latest valid price)

- NAV is computed ONLY on the server; mobile/web render the server value.
- Prices older than the stale window invalidate the snapshot: the snapshot is
  written with ``is_stale=True`` and ``nav=NULL`` — no fabricated valuation.
- Every snapshot records the price timestamp and calculation version.
- A fill triggers a NAV update; Celery recalculates every 30-60s.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import NavSnapshot, utcnow
from packages.live_trading import ledger as ledger_service
from packages.live_trading import price_feed as price_feed_service
from packages.live_trading.gateway_adapter import ExecutionGateway, GatewayError

CALCULATION_VERSION = "1.0.0"

_ZERO = Decimal("0")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _decimal(value, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def calculate_nav(
    db: Session,
    *,
    user_id: str,
    account_id: str,
    mandate_id: str | None = None,
    connection_id: str | None = None,
    gateway: ExecutionGateway | None = None,
    trace_id: str | None = None,
) -> NavSnapshot:
    settings = get_settings()
    positions = ledger_service.position_quantities(db, account_id)

    # Resolve the broker connection when a mandate is known but the caller
    # did not pass it explicitly (e.g. the periodic NAV task).
    if connection_id is None and mandate_id:
        from packages.database.models import TradingMandate

        mandate_row = (
            db.query(TradingMandate).filter_by(id=mandate_id).one_or_none()
        )
        if mandate_row:
            connection_id = mandate_row.broker_connection_id

    # Cash: broker balance when reachable, else ledger-derived cash.
    cash = ledger_service.cash_balance(db, account_id)
    broker_available = None
    if gateway is not None:
        try:
            balances = gateway.account_balances(
                account_id, connection_id=connection_id
            )
            broker_available = _decimal(balances.get("available") or balances.get("cash"))
            cash = broker_available
        except GatewayError:
            pass

    gross = _ZERO
    net = _ZERO
    unrealized = _ZERO
    stale = False
    price_timestamp = None
    missing_prices: list[str] = []

    for symbol, qty in sorted(positions.items()):
        if qty == _ZERO:
            continue
        price, captured_at = price_feed_service.latest_valid_price(
            db, symbol, settings.live_trading_venue,
            stale_seconds=settings.live_nav_price_stale_seconds,
        )
        if price is None:
            stale = True
            missing_prices.append(symbol)
            continue
        value = qty * price
        gross += abs(value)
        net += value
        unrealized += (price - _average_cost(db, account_id, symbol)) * qty
        if price_timestamp is None or (captured_at and captured_at > price_timestamp):
            price_timestamp = captured_at

    nav = None if stale else cash + net
    realized = ledger_service.realized_pnl(db, account_id)

    snapshot = NavSnapshot(
        user_id=user_id,
        account_id=account_id,
        mandate_id=mandate_id,
        nav=nav,
        cash=cash,
        gross_exposure=gross,
        net_exposure=net,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        currency="USD",
        price_timestamp=_aware(price_timestamp) if price_timestamp else None,
        calculated_at=utcnow(),
        is_stale=stale,
        calculation_version=CALCULATION_VERSION,
        reconciliation_status="pending",
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def _average_cost(db: Session, account_id: str, symbol: str) -> Decimal:
    """Simple average cost from trade entries (MVP; no tax lots)."""
    from sqlalchemy import func

    from packages.database.models import LedgerEntry

    buys = (
        db.query(
            func.coalesce(func.sum(LedgerEntry.quantity), 0),
            func.coalesce(func.sum(LedgerEntry.quantity * LedgerEntry.price), 0),
        )
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.symbol == symbol.upper(),
            LedgerEntry.entry_type == "trade_buy",
        )
        .first()
    )
    qty = _decimal(buys[0]) if buys else _ZERO
    cost = _decimal(buys[1]) if buys else _ZERO
    if qty <= _ZERO:
        return _ZERO
    return cost / qty


def latest_snapshot(db: Session, user_id: str, account_id: str) -> NavSnapshot | None:
    return (
        db.query(NavSnapshot)
        .filter_by(user_id=user_id, account_id=account_id)
        .order_by(NavSnapshot.calculated_at.desc())
        .first()
    )


def history(db: Session, user_id: str, account_id: str, *, limit: int = 100) -> list[NavSnapshot]:
    return (
        db.query(NavSnapshot)
        .filter_by(user_id=user_id, account_id=account_id)
        .order_by(NavSnapshot.calculated_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
