"""US equity daily OHLCV loading for research backtests.

Keyed providers only (FMP / Alpha Vantage / Massive), reusing the configured
equity provider chain from ``packages.data.equity_providers``. When no API key
is configured the loader raises :class:`EquityDataUnavailable` so US equity
backtests are explicitly marked UNAVAILABLE — synthetic data is never produced.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

FMP_API_BASE = os.getenv("FMP_API_BASE", "https://financialmodelingprep.com/api/v3").rstrip("/")
ALPHA_VANTAGE_API_BASE = os.getenv("ALPHA_VANTAGE_API_BASE", "https://www.alphavantage.co").rstrip("/")
MASSIVE_API_BASE = os.getenv("MASSIVE_API_BASE", "https://api.polygon.io").rstrip("/")

MAX_BARS = 5000


class EquityDataUnavailable(RuntimeError):
    """Raised when no keyed equity provider can serve daily bars for a symbol."""

    code = "EQUITY_DATA_UNAVAILABLE"

    def __init__(self, symbol: str, reasons: list[str]):
        self.symbol = symbol
        self.reasons = list(reasons)
        detail = "; ".join(self.reasons) if self.reasons else "no keyed equity provider configured"
        super().__init__(f"US equity daily data unavailable for {symbol}: {detail}")


def _day_ts(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _bar(ts: datetime, open_: float, high: float, low: float, close: float, volume: float) -> dict:
    return {"ts": ts, "open": float(open_), "high": float(high), "low": float(low), "close": float(close), "volume": float(volume)}


class EquityDailyLoader:
    """Load daily equity bars from the keyed provider chain. Never synthetic."""

    def __init__(
        self,
        *,
        fmp_api_key: str | None = None,
        alpha_vantage_api_key: str | None = None,
        massive_api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.fmp_api_key = fmp_api_key if fmp_api_key is not None else os.getenv("FMP_API_KEY", "")
        self.alpha_vantage_api_key = (
            alpha_vantage_api_key if alpha_vantage_api_key is not None else os.getenv("ALPHA_VANTAGE_API_KEY", "")
        )
        self.massive_api_key = massive_api_key if massive_api_key is not None else os.getenv("MASSIVE_API_KEY", "")
        self.timeout = timeout

    @property
    def configured_providers(self) -> list[str]:
        providers: list[str] = []
        if self.fmp_api_key:
            providers.append("fmp")
        if self.alpha_vantage_api_key:
            providers.append("alpha_vantage")
        if self.massive_api_key:
            providers.append("massive")
        return providers

    def load_daily(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        """Return ascending daily bars for ``symbol`` between start/end (UTC)."""
        normalized = symbol.upper().strip()
        reasons: list[str] = []
        chain = (
            ("fmp", self.fmp_api_key, self._fmp_daily),
            ("alpha_vantage", self.alpha_vantage_api_key, self._alpha_vantage_daily),
            ("massive", self.massive_api_key, self._massive_daily),
        )
        for name, api_key, fetcher in chain:
            if not api_key:
                reasons.append(f"{name}: no API key configured")
                continue
            try:
                bars = fetcher(normalized, start, end)
            except Exception as exc:  # provider errors are reported, never hidden
                logger.warning("equity_daily provider=%s symbol=%s failed: %s", name, normalized, exc)
                reasons.append(f"{name}: {str(exc)[:160]}")
                continue
            if bars:
                return bars[:MAX_BARS]
            reasons.append(f"{name}: returned no data")
        raise EquityDataUnavailable(normalized, reasons)

    def _fmp_daily(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        response = httpx.get(
            f"{FMP_API_BASE}/historical-price-full/{symbol}",
            params={"from": start.date().isoformat(), "to": end.date().isoformat(), "apikey": self.fmp_api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("historical") or []
        bars = [
            _bar(_day_ts(row["date"]), row["open"], row["high"], row["low"], row["close"], row.get("volume") or 0.0)
            for row in rows
            if row.get("close")
        ]
        bars.sort(key=lambda item: item["ts"])
        return bars

    def _alpha_vantage_daily(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        response = httpx.get(
            f"{ALPHA_VANTAGE_API_BASE}/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": "full",
                "apikey": self.alpha_vantage_api_key,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        series = payload.get("Time Series (Daily)") or {}
        bars = []
        for day, row in series.items():
            ts = _day_ts(day)
            if ts < start or ts > end:
                continue
            bars.append(
                _bar(ts, row["1. open"], row["2. high"], row["3. low"], row["4. close"], row.get("5. volume") or 0.0)
            )
        bars.sort(key=lambda item: item["ts"])
        return bars

    def _massive_daily(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        response = httpx.get(
            f"{MASSIVE_API_BASE}/v2/aggs/ticker/{symbol}/range/1/day/{start.date().isoformat()}/{end.date().isoformat()}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            headers={"Authorization": f"Bearer {self.massive_api_key}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results") or []
        return [
            _bar(datetime.fromtimestamp(int(row["t"]) / 1000, tz=timezone.utc), row["o"], row["h"], row["l"], row["c"], row.get("v") or 0.0)
            for row in rows
            if row.get("c")
        ]
