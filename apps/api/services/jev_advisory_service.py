"""Read-only, fail-closed projection of the runtime's JEV advisory telemetry.

This boundary is not a TypeSafe client: it never evaluates prompts, creates a
signal, or sends an order. The runtime publishes one atomic, normalized JSON
document; it is validated again before a web client can see its status.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.api.config import get_settings

MODEL = "jev-1.13.0"
INSTRUMENT = "BINANCE_PM:BTCUSDC"
SCHEMA = "puregamma.jev_advisory.v1"
MAX_TTL_NS = 5_000_000_000
MAX_U64 = (1 << 64) - 1
CACHE_SECONDS = 2.0


def _record(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _u64_ns(value: object) -> int | None:
    """Parse a canonical nanosecond timestamp without float precision loss."""
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdecimal():
        return None
    if len(value) > 1 and value[0] == "0":
        return None
    parsed = int(value)
    return parsed if parsed <= MAX_U64 else None


def _probability(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and 0 <= parsed <= 1 else None


def _token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _unavailable(status: str, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "status": status,
        "reason": reason,
        "mode": "ADVISORY_ONLY",
        "execution": "DISABLED",
    }


def validate_observation(payload: object, *, now_ns: int) -> dict[str, Any] | None:
    """Return a safe display projection, or None when the contract is invalid."""
    data = _record(payload)
    if (
        data is None
        or data.get("schema") != SCHEMA
        or data.get("model") != MODEL
        or data.get("instrument") != INSTRUMENT
    ):
        return None
    source_ns = _u64_ns(data.get("source_event_ns"))
    received_ns = _u64_ns(data.get("received_ns"))
    expires_ns = _u64_ns(data.get("expires_ns"))
    if (
        source_ns is None
        or received_ns is None
        or expires_ns is None
        or source_ns == 0
        or source_ns > received_ns
        or received_ns > now_ns
        or now_ns >= expires_ns
        or expires_ns <= source_ns
        or expires_ns - source_ns > MAX_TTL_NS
    ):
        return None
    choice = data.get("choice")
    if choice not in {"up", "down", "neutral"}:
        return None
    probabilities = _record(data.get("probabilities"))
    if probabilities is None or set(probabilities) != {"up", "down", "neutral"}:
        return None
    probabilities_safe = {key: _probability(probabilities.get(key)) for key in ("up", "down", "neutral")}
    if any(value is None for value in probabilities_safe.values()):
        return None
    probs = {key: float(value) for key, value in probabilities_safe.items()}
    if abs(sum(probs.values()) - 1.0) > 0.001 or probs[str(choice)] < max(probs.values()) - 0.001:
        return None
    confidence = _probability(data.get("provider_confidence"))
    input_tokens = _token_count(data.get("input_tokens"))
    output_tokens = _token_count(data.get("output_tokens"))
    if confidence is None or input_tokens is None or output_tokens is None:
        return None
    return {
        "available": True,
        "status": "fresh",
        "mode": "ADVISORY_ONLY",
        "execution": "DISABLED",
        "schema": SCHEMA,
        "model": MODEL,
        "instrument": INSTRUMENT,
        "choice": choice,
        "probabilities": probs,
        "provider_confidence": confidence,
        "source_event_ns": str(source_ns),
        "received_ns": str(received_ns),
        "expires_ns": str(expires_ns),
        "age_ms": max(0, (now_ns - received_ns) // 1_000_000),
        "ttl_ms": max(0, (expires_ns - now_ns) // 1_000_000),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


@dataclass
class JevAdvisoryReader:
    path: Path
    _mtime_ns: int | None = None
    _read_at: float = 0.0
    _cached: dict[str, Any] | None = field(default=None)

    def status(self) -> dict[str, Any]:
        settings = get_settings()
        if not settings.jev_advisory_enabled:
            return _unavailable("disabled", "JEV advisory is disabled by the operator")
        if not str(self.path) or str(self.path) == "/nonexistent":
            return _unavailable("unavailable", "No JEV advisory telemetry source is configured")
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return _unavailable("unavailable", "JEV advisory telemetry has not been published")
        except OSError:
            return _unavailable("unavailable", "JEV advisory telemetry cannot be read")

        now_wall = time.time()
        if self._cached is not None and self._mtime_ns == stat.st_mtime_ns and now_wall - self._read_at < CACHE_SECONDS:
            return self._cached
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result = _unavailable("invalid", "JEV advisory telemetry is malformed")
        else:
            result = validate_observation(payload, now_ns=time.time_ns())
            if result is None:
                result = _unavailable("invalid_or_stale", "JEV advisory telemetry failed validation or expired")
        self._mtime_ns = stat.st_mtime_ns
        self._read_at = now_wall
        self._cached = result
        return result


_reader: JevAdvisoryReader | None = None
_reader_path: str | None = None


def get_reader() -> JevAdvisoryReader:
    global _reader, _reader_path
    path = get_settings().jev_advisory_telemetry_path
    if _reader is None or _reader_path != path:
        _reader = JevAdvisoryReader(Path(path) if path else Path("/nonexistent"))
        _reader_path = path
    return _reader


def reset_reader_cache() -> None:
    global _reader, _reader_path
    _reader = None
    _reader_path = None
