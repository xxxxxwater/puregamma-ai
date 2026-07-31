"""
NautilusTrader Data Catalog Adapter

Bridges PureGamma's synchronized data pipelines (Binance, DefiLlama, EVM RPC,
The Graph) into NautilusTrader's DataCatalog for use by its BacktestEngine
and strategy framework.

Architecture:
  PureGamma DB (MarketQuoteRecord, DefiMetric, OnchainMetric)
       │
       ▼
  NautilusDataAdapter (this module)
       │  ┌─ bars_to_catalog()
       │  ├─ instruments_for_symbols()
       │  └─ catalog_from_db()
       ▼
  nautilus_trader.model.data.Bar → nautilus_trader.data.catalog.DataCatalog
       │
       ▼
  nautilus_trader.backtest.engine.BacktestEngine
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from packages.database.models import DataSource, MarketQuoteRecord


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime(2024, 1, 1, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def instruments_for_symbols(symbols: list[str]) -> list[dict]:
    """Return NautilusTrader-compatible instrument definitions."""
    instruments: list[dict] = []
    for symbol in symbols:
        upper = symbol.upper().strip()
        if not upper:
            continue
        if upper in ("BTC", "ETH"):
            prec = 2
        elif upper in ("SOL", "HYPE"):
            prec = 3
        else:
            prec = 4
        instruments.append(
            {
                "id": f"{upper}USDT-PERP.BINANCE",
                "symbol": upper,
                "base_currency": upper,
                "quote_currency": "USDT",
                "exchange": "BINANCE",
                "price_precision": prec,
                "size_precision": 6,
                "min_notional": 10.0,
                "maker_fee": 0.001,
                "taker_fee": 0.001,
            }
        )
    return instruments


def bars_from_db(
    db: Session,
    symbol: str,
    lookback_days: int = 90,
) -> list[dict]:
    """Extract historical bars from MarketQuoteRecord table.

    Returns NautilusTrader-compatible Bar dicts sorted by timestamp ascending.
    """
    rows = (
        db.query(MarketQuoteRecord)
        .filter(
            MarketQuoteRecord.base_asset == symbol.upper(),
            MarketQuoteRecord.provider == "binance",
        )
        .order_by(MarketQuoteRecord.fetched_at.desc())
        .limit(lookback_days * 24)
        .all()
    )
    rows.reverse()

    bars: list[dict] = []
    for row in rows:
        ts = _ensure_utc(row.source_timestamp or row.fetched_at)
        close = _safe_float(row.price)
        if close <= 0:
            continue
        high = close * 1.002
        low = close * 0.998
        open_price = (
            close * 1.001 if bars and close > bars[-1]["close"] else close * 0.999
        )
        volume = _safe_float(row.volume_24h_base) / 24.0 if row.volume_24h_base else 0.0
        bars.append(
            {
                "bar_type": f"{symbol}USDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
                "open": round(open_price, 8),
                "high": round(high, 8),
                "low": round(low, 8),
                "close": round(close, 8),
                "volume": round(volume, 8),
                "ts_event_ns": int(ts.timestamp() * 1e9),
                "ts_init_ns": int(ts.timestamp() * 1e9),
            }
        )
    return bars


def catalog_from_db(
    db: Session,
    symbols: list[str],
    lookback_days: int = 90,
) -> dict:
    """Build a NautilusTrader-compatible DataCatalog from PureGamma DB."""
    instruments = instruments_for_symbols(symbols)
    all_bars: dict[str, list[dict]] = {}
    for symbol in symbols:
        bars = bars_from_db(db, symbol, lookback_days)
        if bars:
            all_bars[f"{symbol}USDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"] = bars

    sources = {
        row.id: row.status
        for row in db.query(DataSource)
        .filter(
            DataSource.id.in_(["binance", "defillama-free", "evm-rpc", "the-graph"])
        )
        .all()
    }
    healthy = all(v == "healthy" for v in sources.values())
    degraded_sources = [k for k, v in sources.items() if v != "healthy"]

    return {
        "instruments": instruments,
        "bars": all_bars,
        "bar_count": sum(len(b) for b in all_bars.values()),
        "symbols": symbols,
        "lookback_days": lookback_days,
        "data_freshness": "healthy" if healthy else "degraded",
        "degraded_sources": degraded_sources,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar_construction": "synthetic_ohlc_from_point_quotes",
    }


def mock_catalog(symbols: list[str] | None = None, bar_count: int = 720) -> dict:
    """Generate a synthetic DataCatalog for development/testing."""
    import random

    random.seed(42)
    symbols = symbols or ["BTC", "ETH"]
    instruments = instruments_for_symbols(symbols)
    all_bars: dict[str, list[dict]] = {}
    base_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1e9)
    hour_ns = int(3.6e12)

    for symbol in symbols:
        price = 50000.0 if symbol == "BTC" else 3000.0 if symbol == "ETH" else 100.0
        bars: list[dict] = []
        for i in range(bar_count):
            change = random.gauss(0, 0.008)
            open_price = price
            close = price * (1 + change)
            high = max(open_price, close) * (1 + abs(random.gauss(0, 0.003)))
            low = min(open_price, close) * (1 - abs(random.gauss(0, 0.003)))
            volume = abs(random.gauss(100, 30))
            ts = base_ts + i * hour_ns
            bars.append(
                {
                    "bar_type": f"{symbol}USDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": round(volume, 4),
                    "ts_event_ns": ts,
                    "ts_init_ns": ts,
                }
            )
            price = close
        all_bars[f"{symbol}USDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"] = bars

    return {
        "instruments": instruments,
        "bars": all_bars,
        "bar_count": sum(len(b) for b in all_bars.values()),
        "symbols": symbols,
        "lookback_days": bar_count // 24,
        "data_freshness": "mock",
        "degraded_sources": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar_construction": "synthetic_fixture",
    }
