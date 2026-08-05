"""Shared daily OHLCV download for the backtest lab.

Downloads 1d klines from the unified Binance REST endpoint and persists them
idempotently into ``backtest_candles`` so every user backtest reuses one
canonical three-year BTC/ETH dataset instead of re-fetching per run.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from packages.database.models import BacktestCandle

LAB_SYMBOLS: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "HYPE": "HYPEUSDT",
}
# Assets whose daily candles come from the Hyperliquid info API (Binance spot
# does not list them); everything else in LAB_SYMBOLS uses Binance spot.
HYPERLIQUID_ASSETS: dict[str, str] = {
    "HYPE": "HYPE",
}
KLINES_LIMIT = 1000
DEFAULT_LOOKBACK_DAYS = 365 * 3


def is_crypto_asset(asset: str) -> bool:
    """True when the asset is served by the shared daily candle store."""
    return asset.upper().strip() in LAB_SYMBOLS


def provider_for_asset(asset: str) -> str:
    """Real upstream venue for an asset's daily candles."""
    return "hyperliquid" if asset.upper().strip() in HYPERLIQUID_ASSETS else "binance"


def _base_url() -> str:
    return (os.getenv("BINANCE_REST_BASE_URL") or "https://api.binance.com").rstrip("/")


def _hyperliquid_url() -> str:
    return (os.getenv("HYPERLIQUID_REST_BASE_URL") or "https://api.hyperliquid.xyz").rstrip("/")


def _fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list[list]:
    rows: list[list] = []
    cursor = start_ms
    with httpx.Client(timeout=15.0) as client:
        while cursor < end_ms:
            response = client.get(
                f"{_base_url()}/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": "1d",
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": KLINES_LIMIT,
                },
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            rows.extend(batch)
            last_open_time = int(batch[-1][0])
            cursor = last_open_time + 86_400_000
            if len(batch) < KLINES_LIMIT:
                break
    return rows


def _fetch_hyperliquid_daily(coin: str, start_ms: int, end_ms: int) -> list[list]:
    """Daily candles from the Hyperliquid info API, shaped like Binance klines.

    Response rows are ``{t, T, s, i, o, c, h, l, v, n}``; we map them onto the
    Binance kline positions used by the upsert path (open time, o/h/l/c, volume).
    """
    rows: list[list] = []
    cursor = start_ms
    with httpx.Client(timeout=15.0) as client:
        while cursor < end_ms:
            response = client.post(
                f"{_hyperliquid_url()}/info",
                json={
                    "type": "candleSnapshot",
                    "req": {"coin": coin, "interval": "1d", "startTime": cursor, "endTime": end_ms},
                },
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            for item in batch:
                rows.append([
                    int(item["t"]),
                    item["o"],
                    item["h"],
                    item["l"],
                    item["c"],
                    item["v"],
                ])
            last_open_time = int(batch[-1]["t"])
            cursor = last_open_time + 86_400_000
            if len(batch) < 2:
                break
    rows.sort(key=lambda item: int(item[0]))
    # De-duplicate by open time (overlapping pages).
    seen: set[int] = set()
    unique: list[list] = []
    for item in rows:
        if int(item[0]) in seen:
            continue
        seen.add(int(item[0]))
        unique.append(item)
    return unique


def refresh_daily_candles(
    db: Session,
    assets: list[str] | None = None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict:
    """Idempotently backfill/extend the shared daily candle dataset."""
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    stats: dict[str, dict[str, int]] = {}
    for asset in (assets or list(LAB_SYMBOLS)):
        symbol = LAB_SYMBOLS.get(asset.upper())
        if not symbol:
            continue
        latest = (
            db.query(BacktestCandle.ts)
            .filter(BacktestCandle.symbol == symbol, BacktestCandle.interval == "1d")
            .order_by(BacktestCandle.ts.desc())
            .first()
        )
        start_dt = (latest[0] + timedelta(days=1)) if latest else (now - timedelta(days=lookback_days))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        start_ms = int(start_dt.timestamp() * 1000)
        if start_ms >= end_ms - 86_400_000:
            stats[symbol] = {"fetched": 0, "upserted": 0}
            continue
        provider = provider_for_asset(asset)
        if provider == "hyperliquid":
            raw = _fetch_hyperliquid_daily(HYPERLIQUID_ASSETS[asset.upper()], start_ms, end_ms)
        else:
            raw = _fetch_klines(symbol, start_ms, end_ms)
        upserted = 0
        for item in raw:
            ts = datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc)
            values = {
                "symbol": symbol,
                "interval": "1d",
                "ts": ts,
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "provider": provider,
                "fetched_at": now,
            }
            if db.bind and db.bind.dialect.name == "postgresql":
                stmt = pg_insert(BacktestCandle.__table__).values(id=f"btcl-{symbol}-{int(item[0])}", **values)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_backtest_candle_symbol_interval_ts",
                    set_={key: values[key] for key in ("open", "high", "low", "close", "volume", "provider", "fetched_at")},
                )
                db.execute(stmt)
            else:
                existing = (
                    db.query(BacktestCandle)
                    .filter_by(symbol=symbol, interval="1d", ts=ts)
                    .one_or_none()
                )
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    db.add(BacktestCandle(id=f"btcl-{symbol}-{int(item[0])}", **values))
            upserted += 1
        stats[symbol] = {"fetched": len(raw), "upserted": upserted}
    db.commit()
    return stats


def load_candle_window(
    db: Session,
    assets: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, list[dict]]:
    """Return ascending daily bars per asset for the backtest window."""
    series: dict[str, list[dict]] = {}
    for asset in assets:
        symbol = LAB_SYMBOLS.get(asset.upper())
        if not symbol:
            series[asset.upper()] = []
            continue
        rows = (
            db.query(BacktestCandle)
            .filter(
                BacktestCandle.symbol == symbol,
                BacktestCandle.interval == "1d",
                BacktestCandle.ts >= start,
                BacktestCandle.ts <= end,
            )
            .order_by(BacktestCandle.ts.asc())
            .all()
        )
        series[asset.upper()] = [
            {"ts": row.ts, "open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume}
            for row in rows
        ]
    return series


def candle_coverage(db: Session) -> dict[str, dict[str, object]]:
    coverage: dict[str, dict[str, object]] = {}
    for asset, symbol in LAB_SYMBOLS.items():
        rows = (
            db.query(BacktestCandle)
            .filter(BacktestCandle.symbol == symbol, BacktestCandle.interval == "1d")
            .order_by(BacktestCandle.ts.asc())
            .all()
        )
        coverage[asset] = {
            "bars": len(rows),
            "first_ts": rows[0].ts.isoformat() if rows else None,
            "last_ts": rows[-1].ts.isoformat() if rows else None,
        }
    return coverage
