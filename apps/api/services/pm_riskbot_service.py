"""Read-only access to the Binance Portfolio Margin bundle published by riskbot.

Architecture (deliberately one-directional):

    Binance  ---->  riskbot  ---->  export bundle  ---->  PureGamma API  ---->  UI
                    (owns the        (JSON files,          (this module;
                     read-only        atomically           never holds an
                     API key)         replaced)             exchange key)

PureGamma holds **no** Binance credentials for this account: it reads files that
riskbot writes into a directory mounted read-only.  That keeps the trading
account unreachable from the web tier and means a PureGamma compromise cannot
place, cancel or transfer anything.

Two invariants are enforced here:

* **Authorization is server-side.**  ``allowed_emails()`` is the single source of
  truth and every route that touches PM data depends on it; hiding UI is never
  treated as access control.
* **Nothing is fabricated.**  If the bundle is missing or old, the reader
  reports ``available: false`` with the reason instead of inventing zeros, and
  the NAV series is returned exactly as observed (gaps included).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.api.config import get_settings

logger = logging.getLogger(__name__)

LATEST_SCHEMA = "puregamma.pm_account.v1"
SERIES_SCHEMA = "puregamma.pm_nav_series.v1"

#: Hard cap on how long a cached read may serve the response, so an operator
#: never sees an unbounded-stale page if the file mtime is misleading.
MAX_CACHE_SECONDS = 5.0
#: Bundles older than this are reported as stale (riskbot reconciles every 60s).
STALE_AFTER_SECONDS = 180.0


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def allowed_emails() -> tuple[str, ...]:
    """The only accounts permitted to read this PM account.

    Configured through ``PM_ACCOUNT_ALLOWED_EMAILS``; the default names the
    owner's own accounts.  Empty configuration means *deny everyone* -
    a misconfiguration must fail closed, never open.
    """
    raw = get_settings().pm_account_allowed_emails or ""
    emails = tuple(
        normalize_email(part) for part in raw.replace(";", ",").split(",") if part.strip()
    )
    return tuple(dict.fromkeys(emails))


def is_allowed_email(email: str | None) -> bool:
    candidate = normalize_email(email)
    if not candidate:
        return False
    return candidate in allowed_emails()


@dataclass
class BundleRead:
    """Result of reading one bundle file."""

    data: dict[str, Any] | None
    path: str
    error: str | None = None
    mtime: float | None = None

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None


@dataclass
class _CacheEntry:
    mtime: float
    size: int
    read_at: float
    data: dict[str, Any] | None
    error: str | None = None


@dataclass
class PmAccountReader:
    directory: Path
    _cache: dict[str, _CacheEntry] = field(default_factory=dict)

    def _read(self, filename: str, schema: str) -> BundleRead:
        path = self.directory / filename
        cached = self._cache.get(filename)
        try:
            stat = path.stat()
        except FileNotFoundError:
            # Keep serving the last good copy only if it is recent; otherwise
            # report the outage rather than a stale page presented as live.
            if cached is not None and time.time() - cached.read_at <= STALE_AFTER_SECONDS:
                return BundleRead(data=cached.data, path=str(path), mtime=cached.mtime,
                                  error=cached.error)
            return BundleRead(data=None, path=str(path),
                              error="riskbot export bundle not found")
        except OSError as exc:
            return BundleRead(data=None, path=str(path), error=f"unreadable: {exc}")
        if (
            cached is not None
            and cached.mtime == stat.st_mtime
            and cached.size == stat.st_size
            and time.time() - cached.read_at < MAX_CACHE_SECONDS
        ):
            return BundleRead(data=cached.data, path=str(path), mtime=cached.mtime,
                              error=cached.error)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            # A torn read cannot happen (riskbot writes tmp+rename) but a
            # malformed file must be reported, not guessed around.
            logger.warning("pm bundle %s unreadable: %s", path, exc)
            return BundleRead(data=None, path=str(path), error=f"malformed bundle: {exc}")
        if not isinstance(data, dict):
            return BundleRead(data=None, path=str(path), error="bundle is not an object")
        declared = data.get("schema")
        if declared != schema:
            logger.warning("pm bundle %s has schema %r, expected %r", path, declared, schema)
            return BundleRead(data=None, path=str(path),
                              error=f"unsupported bundle schema {declared!r}")
        self._cache[filename] = _CacheEntry(mtime=stat.st_mtime, size=stat.st_size,
                                            read_at=time.time(), data=data)
        return BundleRead(data=data, path=str(path), mtime=stat.st_mtime)

    def latest(self) -> BundleRead:
        return self._read("latest.json", LATEST_SCHEMA)

    def series(self) -> BundleRead:
        return self._read("series.json", SERIES_SCHEMA)

    # ------------------------------------------------------------------ views
    def account_view(self) -> dict[str, Any]:
        """Everything the NAV page needs, plus honest freshness metadata."""
        latest = self.latest()
        if not latest.ok or latest.data is None:
            return {
                "available": False,
                "reason": latest.error or "unavailable",
                "source": {"collector": "riskbot", "read_only": True},
                "bundle_path": latest.path,
            }
        payload = latest.data
        snapshot = payload.get("snapshot") or {}
        quality = payload.get("quality") or {}
        coverage = payload.get("coverage") or {}
        age_seconds = self._age_seconds(snapshot, latest.mtime)
        stale = age_seconds is not None and age_seconds > STALE_AFTER_SECONDS
        orders_meta = payload.get("orders_meta") or {}
        risk = payload.get("risk") or {}
        return {
            "available": True,
            "stale": bool(stale or snapshot.get("is_stale")),
            "partial": bool(snapshot.get("partial") or quality.get("partial")),
            "age_seconds": age_seconds,
            "stale_after_seconds": STALE_AFTER_SECONDS,
            "data_as_of": snapshot.get("captured_at") or payload.get("generated_at"),
            "generated_at": payload.get("generated_at"),
            "collector": payload.get("collector") or {},
            "source": {
                "collector": (payload.get("collector") or {}).get("name", "riskbot"),
                "read_only": (payload.get("collector") or {}).get("read_only", True),
                "independent_of_trading_bot": (payload.get("collector") or {}).get(
                    "independent_of_trading_bot", True),
                "venue": "Binance Portfolio Margin (Classic)",
                "note": ("只读采集，PureGamma 不持有该账户的任何 API Key，"
                         "也不具备下单/撤单能力"),
            },
            # Official exchange figures, kept names intact.
            "account": payload.get("account") or {},
            # Real BTC quantity vs BTC-equivalent of USD figures.
            "btc": payload.get("btc") or {},
            "exposure": payload.get("exposure") or {},
            "balances": payload.get("balances") or [],
            "positions": payload.get("positions") or [],
            # Position lifecycle history (snapshot-diff derived, newest first).
            "positions_history": payload.get("positions_history") or [],
            "positions_history_meta": payload.get("positions_history_meta") or {},
            "orders": payload.get("orders") or [],
            "orders_meta": {
                "captured_at": orders_meta.get("captured_at"),
                "age_seconds": orders_meta.get("age_seconds"),
                "fully_covered": orders_meta.get("fully_covered"),
                "refresh_interval_seconds": orders_meta.get("refresh_interval_seconds"),
            },
            "protection": payload.get("protection") or [],
            "risk": {
                "firing_count": risk.get("firing_count", 0),
                "firing": risk.get("firing") or [],
                "drawdown_peak_btc_equivalent": risk.get("drawdown_peak_btc_equivalent"),
                "drawdown_day_btc_equivalent": risk.get("drawdown_day_btc_equivalent"),
            },
            "coverage": {
                "essential_ok": coverage.get("essential_ok"),
                "orders_covered": coverage.get("orders_covered"),
                "failures": coverage.get("failures") or [],
                "essential_failures": coverage.get("essential_failures") or [],
            },
            "quality": {
                "rest_ok": quality.get("rest_ok"),
                "ws_connected": quality.get("ws_connected"),
                "mismatch": quality.get("mismatch"),
                "last_error": quality.get("last_error"),
            },
            "disclaimer": payload.get("disclaimer"),
        }

    def nav_history_view(self) -> dict[str, Any]:
        series = self.series()
        if not series.ok or series.data is None:
            return {
                "available": False,
                "reason": series.error or "unavailable",
                "points": [],
                "point_count": 0,
                "interval_hint_seconds": None,
            }
        payload = series.data
        points = payload.get("points") or []
        return {
            "available": True,
            "schema": payload.get("schema"),
            "generated_at": payload.get("generated_at"),
            "first_point_at": payload.get("first_point_at"),
            "point_count": payload.get("point_count", len(points)),
            # Reported so the UI can say "数据不足" instead of drawing one dot.
            "sufficient": len(points) >= 2,
            "window_days": payload.get("window_days"),
            "interval_hint_seconds": payload.get("interval_hint_seconds"),
            "sampling": payload.get("sampling"),
            "points": points,
        }

    @staticmethod
    def _age_seconds(snapshot: dict[str, Any], mtime: float | None) -> float | None:
        """Age of the observation, measured from the reader's own clock.

        ``snapshot.age_seconds`` is relative to riskbot's process clock, which
        is meaningless here; the file mtime is what this process can verify.
        """
        if mtime is not None:
            return max(0.0, time.time() - mtime)
        captured = snapshot.get("captured_at_ms")
        if isinstance(captured, (int, float)) and captured > 0:
            return max(0.0, time.time() - float(captured) / 1000.0)
        return None


_reader: PmAccountReader | None = None
_reader_dir: str | None = None


def get_reader() -> PmAccountReader:
    """Process-wide reader bound to the configured export directory."""
    global _reader, _reader_dir
    directory = get_settings().pm_riskbot_export_dir or ""
    if _reader is None or _reader_dir != directory:
        _reader = PmAccountReader(directory=Path(directory or "/nonexistent"))
        _reader_dir = directory
    return _reader


def reset_reader_cache() -> None:
    """Drop the cached bundle (tests / config reload)."""
    global _reader, _reader_dir
    _reader = None
    _reader_dir = None
