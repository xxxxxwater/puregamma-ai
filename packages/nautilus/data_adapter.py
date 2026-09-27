"""
NautilusTrader Data Catalog Adapter

Bridges synchronized PureGamma market-point history into a
NautilusTrader-compatible research catalog.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
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


def timeframe_minutes(timeframe: str) -> int:
    value = str(timeframe or "1h").strip().lower()
    match = re.fullmatch(r"(\d{1,4})(m|h|d)", value)
    if not match:
        raise ValueError("BACKTEST_TIMEFRAME_INVALID")
    count = int(match.group(1))
    unit = match.group(2)
    if count <= 0:
        raise ValueError("BACKTEST_TIMEFRAME_INVALID")
    minutes = count if unit == "m" else count * 60 if unit == "h" else count * 1440
    if minutes > 10080:
        raise ValueError("BACKTEST_TIMEFRAME_TOO_LARGE")
    return minutes


def _bar_interval_label(timeframe: str) -> str:
    minutes = timeframe_minutes(timeframe)
    if minutes % 1440 == 0:
        return f"{minutes // 1440}-DAY"
    if minutes % 60 == 0:
        return f"{minutes // 60}-HOUR"
    return f"{minutes}-MINUTE"


def instruments_for_symbols(symbols: list[str]) -> list[dict]:
    instruments: list[dict] = []
    for symbol in symbols:
        upper = symbol.upper().strip()
        if not upper:
            continue
        prec = 2 if upper in ("BTC", "ETH") else 3 if upper in ("SOL", "HYPE") else 4
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


def _derivative_value(row: MarketQuoteRecord, key: str) -> float | None:
    provenance = dict(row.provenance_json or {})
    derivatives = provenance.get("derivatives") or {}
    aliases = {
        "funding_rate": ("funding_rate", "fundingRate"),
        "open_interest": ("open_interest", "openInterest"),
    }
    for alias in aliases.get(key, (key,)):
        if alias in derivatives and derivatives.get(alias) is not None:
            try:
                return float(derivatives[alias])
            except (TypeError, ValueError):
                return None
    return None


def factor_coverage_from_bars(bars: list[dict]) -> dict[str, float]:
    if not bars:
        return {"close": 0.0, "volume": 0.0, "bid_ask": 0.0, "funding_rate": 0.0, "open_interest": 0.0}
    total = len(bars)
    checks = {
        "close": lambda bar: float(bar.get("close") or 0.0) > 0,
        "volume": lambda bar: float(bar.get("volume") or 0.0) > 0,
        "bid_ask": lambda bar: float(bar.get("bid") or 0.0) > 0 and float(bar.get("ask") or 0.0) >= float(bar.get("bid") or 0.0),
        "funding_rate": lambda bar: bar.get("funding_rate") is not None,
        "open_interest": lambda bar: float(bar.get("open_interest") or 0.0) > 0,
    }
    return {key: round(sum(1 for bar in bars if predicate(bar)) / total, 4) for key, predicate in checks.items()}


def bars_from_db(
    db: Session,
    symbol: str,
    lookback_days: int = 90,
    timeframe: str = "1h",
) -> list[dict]:
    """Aggregate synchronized point quotes into causal research bars."""
    minutes = timeframe_minutes(timeframe)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))
    expected = max(1, int(lookback_days * 1440 / minutes))
    query_limit = min(50_000, max(500, expected * 6))
    rows = (
        db.query(MarketQuoteRecord)
        .filter(
            MarketQuoteRecord.base_asset == symbol.upper(),
            MarketQuoteRecord.provider == "binance",
            MarketQuoteRecord.fetched_at >= cutoff,
        )
        .order_by(MarketQuoteRecord.fetched_at.desc())
        .limit(query_limit)
        .all()
    )
    rows.reverse()
    bucket_seconds = minutes * 60
    buckets: dict[int, list[dict]] = {}
    intervals_per_day = max(1.0, 1440.0 / minutes)
    for row in rows:
        ts = _ensure_utc(row.source_timestamp or row.fetched_at)
        close = _safe_float(row.price)
        if close <= 0:
            continue
        volume = _safe_float(row.volume_24h_base) / intervals_per_day if row.volume_24h_base else 0.0
        bucket = int(ts.timestamp()) // bucket_seconds
        buckets.setdefault(bucket, []).append({
            "ts": ts,
            "close": close,
            "volume": volume,
            "bid": _safe_float(row.bid) or None,
            "ask": _safe_float(row.ask) or None,
            "funding_rate": _derivative_value(row, "funding_rate"),
            "open_interest": _derivative_value(row, "open_interest"),
        })

    interval_label = _bar_interval_label(timeframe)
    bars: list[dict] = []
    for bucket in sorted(buckets):
        points = sorted(buckets[bucket], key=lambda item: item["ts"])
        prices = [float(item["close"]) for item in points]
        latest = points[-1]
        ts_ns = int(bucket * bucket_seconds * 1e9)
        bars.append({
            "bar_type": f"{symbol}USDT-PERP.BINANCE-{interval_label}-LAST-EXTERNAL",
            "open": round(prices[0], 8),
            "high": round(max(prices), 8),
            "low": round(min(prices), 8),
            "close": round(prices[-1], 8),
            "volume": round(float(latest["volume"]), 8),
            "bid": latest.get("bid"),
            "ask": latest.get("ask"),
            "funding_rate": latest.get("funding_rate"),
            "open_interest": latest.get("open_interest"),
            "ts_event_ns": ts_ns,
            "ts_init_ns": ts_ns,
        })
    return bars

def catalog_from_db(
    db: Session,
    symbols: list[str],
    lookback_days: int = 90,
    timeframe: str = "1h",
) -> dict:
    instruments = instruments_for_symbols(symbols)
    all_bars: dict[str, list[dict]] = {}
    interval_label = _bar_interval_label(timeframe)
    for symbol in symbols:
        bars = bars_from_db(db, symbol, lookback_days, timeframe)
        if bars:
            all_bars[f"{symbol}USDT-PERP.BINANCE-{interval_label}-LAST-EXTERNAL"] = bars

    sources = {
        row.id: row.status
        for row in db.query(DataSource)
        .filter(DataSource.id.in_(["binance", "defillama-free", "evm-rpc", "the-graph"]))
        .all()
    }
    healthy = bool(sources) and all(v == "healthy" for v in sources.values())
    degraded_sources = [k for k, v in sources.items() if v != "healthy"]

    minutes = timeframe_minutes(timeframe)
    expected_bars = max(1, int(max(1, lookback_days) * 1440 / minutes))
    bar_count = sum(len(b) for b in all_bars.values())
    coverage_ratio = min(
        1.0,
        bar_count / max(1, expected_bars * max(1, len(symbols))),
    )
    freshness = "healthy" if healthy and coverage_ratio >= 0.70 else "degraded"
    flattened_bars = [bar for values in all_bars.values() for bar in values]
    factor_coverage = factor_coverage_from_bars(flattened_bars)
    return {
        "instruments": instruments,
        "bars": all_bars,
        "bar_count": bar_count,
        "symbols": symbols,
        "lookback_days": lookback_days,
        "timeframe": timeframe,
        "coverage_ratio": round(coverage_ratio, 4),
        "expected_bar_count": expected_bars * max(1, len(symbols)),
        "data_freshness": freshness,
        "degraded_sources": degraded_sources,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar_construction": "ohlc_from_synchronized_point_quotes; volume_estimated_from_24h; bid_ask_last_in_bucket; funding_oi_from_public_perp_snapshots",
        "factor_coverage": factor_coverage,
        "factor_quality": {
            "vwap": "rolling_24h_volume_proxy",
            "orderflow": "signed_volume_quote_proxy",
            "funding_oi": "public_perpetual_snapshot",
        },
    }


def mock_catalog(
    symbols: list[str] | None = None,
    bar_count: int = 720,
    timeframe: str = "1h",
) -> dict:
    import random

    random.seed(42)
    symbols = symbols or ["BTC", "ETH"]
    instruments = instruments_for_symbols(symbols)
    all_bars: dict[str, list[dict]] = {}
    base_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1e9)
    minutes = timeframe_minutes(timeframe)
    step_ns = int(minutes * 60 * 1e9)
    interval_label = _bar_interval_label(timeframe)

    for symbol in symbols:
        price = 50000.0 if symbol == "BTC" else 3000.0 if symbol == "ETH" else 100.0
        open_interest = 1_000_000.0 if symbol == "BTC" else 300_000.0
        bars: list[dict] = []
        for i in range(bar_count):
            change = random.gauss(0, 0.008)
            open_price = price
            close = price * (1 + change)
            high = max(open_price, close) * (1 + abs(random.gauss(0, 0.003)))
            low = min(open_price, close) * (1 - abs(random.gauss(0, 0.003)))
            volume = abs(random.gauss(100, 30))
            open_interest = max(1.0, open_interest * (1 + random.gauss(0, 0.01)))
            funding_rate = random.gauss(0, 0.00008)
            spread = max(0.01, close * 0.0001)
            ts = base_ts + i * step_ns
            bars.append(
                {
                    "bar_type": f"{symbol}USDT-PERP.BINANCE-{interval_label}-LAST-EXTERNAL",
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": round(volume, 4),
                    "bid": round(close - spread / 2, 8),
                    "ask": round(close + spread / 2, 8),
                    "funding_rate": round(funding_rate, 8),
                    "open_interest": round(open_interest, 4),
                    "ts_event_ns": ts,
                    "ts_init_ns": ts,
                }
            )
            price = close
        all_bars[f"{symbol}USDT-PERP.BINANCE-{interval_label}-LAST-EXTERNAL"] = bars

    return {
        "instruments": instruments,
        "bars": all_bars,
        "bar_count": sum(len(b) for b in all_bars.values()),
        "symbols": symbols,
        "lookback_days": max(1, int(bar_count * minutes / 1440)),
        "timeframe": timeframe,
        "coverage_ratio": 1.0,
        "expected_bar_count": bar_count * len(symbols),
        "data_freshness": "mock",
        "degraded_sources": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar_construction": "synthetic_fixture",
        "factor_coverage": {"close": 1.0, "volume": 1.0, "bid_ask": 1.0, "funding_rate": 1.0, "open_interest": 1.0},
        "factor_quality": {"vwap": "synthetic_fixture", "orderflow": "synthetic_fixture", "funding_oi": "synthetic_fixture"},
    }
