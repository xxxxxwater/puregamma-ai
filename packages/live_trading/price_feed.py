"""Server-recorded market prices for NAV marking.

Prices are only recorded by server processes (runtime/gateway sync tasks);
client-provided prices are never accepted. Read paths evaluate staleness
against the configured window and return None instead of fabricating.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import MarketPriceSnapshot, utcnow


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def record_price(
    db: Session,
    *,
    symbol: str,
    price: Decimal | float | str,
    venue: str = "MOCK",
    source: str = "runtime",
    captured_at: datetime | None = None,
    trace_id: str | None = None,
) -> MarketPriceSnapshot:
    row = MarketPriceSnapshot(
        symbol=symbol.upper(),
        venue=(venue or "MOCK").upper(),
        price=Decimal(str(price)),
        captured_at=_aware(captured_at or utcnow()),
        source=source,
        trace_id=trace_id,
    )
    db.add(row)
    db.flush()
    return row


def latest_valid_price(
    db: Session,
    symbol: str,
    venue: str = "MOCK",
    *,
    stale_seconds: int | None = None,
) -> tuple[Decimal | None, datetime | None]:
    """Latest price within the stale window; (None, None) when no valid price
    exists so callers can never fabricate a valuation."""
    window = stale_seconds if stale_seconds is not None else max(
        1, get_settings().live_nav_price_stale_seconds
    )
    cutoff = utcnow() - timedelta(seconds=window)
    row = (
        db.query(MarketPriceSnapshot)
        .filter(
            MarketPriceSnapshot.symbol == symbol.upper(),
            MarketPriceSnapshot.venue == (venue or "MOCK").upper(),
            MarketPriceSnapshot.captured_at >= cutoff,
        )
        .order_by(desc(MarketPriceSnapshot.captured_at))
        .first()
    )
    if not row or row.price is None:
        return None, None
    return Decimal(str(row.price)), _aware(row.captured_at)
