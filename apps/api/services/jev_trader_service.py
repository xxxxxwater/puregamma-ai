"""Shared ingestion of the third-party Jev Trader live feed.

Why this exists
---------------
The public demo exposes its own SSE stream. Having every PureGamma browser open
its own upstream connection would multiply load on a free-tier Railway
container we do not control, and would put that container on the critical path
of our own page. So exactly one process-wide upstream connection is opened
here, normalised once, and fanned out to every subscriber.

Design notes that matter
------------------------
**The upstream deployment is not its HEAD.** The live payload carries
``totals`` as a positional *array* and has no ``quote``/``resting`` fields,
while the repository's current `server.ts` has a different shape entirely. The
adapter below binds to the *observed* shape, and names array positions only
when the length matches exactly what was verified -- a shifted array must
produce a schema mismatch, never a wrong statistic. See
``docs/audit/JEV_TRADER_AUDIT.md``.

**No ping.** The deployed build was not observed to emit the heartbeat the
HEAD source sends, so liveness is judged by *event arrival time*, not by a
heartbeat. Connection state and data freshness are tracked separately: a
connection can be open while the feed is quiet.

**Bounded everywhere.** The ring buffer, the subscriber wait, and the retry
backoff are all capped. Nothing here grows with the number of events seen.

**Read-only, and isolated.** This module only ever issues GETs against one
configured host. It never touches Binance PM, Freqtrade, Nautilus, or any
trading state.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections import deque
from typing import Any, Iterator

import httpx

from apps.api.config import get_settings

logger = logging.getLogger(__name__)

#: Schema version of the *normalised* payload this module emits. Bump whenever
#: the emitted shape changes so a cached client can detect it.
SCHEMA_VERSION = "puregamma.jev_trader.v1"

#: Upstream `totals` keys as observed on the live deployment, mapped to the
#: names this service publishes.
#:
#: CORRECTION (verified against the live payload): `totals` is a JSON *object*
#: with named keys, not the positional array the P1 audit recorded. Named keys
#: are strictly safer -- there is no index to shift -- so they are the primary
#: path and the array form below is kept only as a defensive fallback.
TOTALS_KEYS: dict[str, str] = {
    "blocks": "blocks",
    "decisions": "decisions",
    "trades": "trades",
    "lateBlocks": "late_blocks",
    "jevUsd": "jev_usd",
    "gasMon": "gas_mon",
    "gasUsd": "gas_usd",
    "realizedUsd": "realized_usd",
    "pnlUsd": "pnl_usd",
    "pnlMon": "pnl_mon",
    "pnlPct": "pnl_pct",
}

#: Positional layout, used only if an upstream ever sends `totals` as a list.
#: Kept from the original audit for compatibility; the object form is what the
#: live feed actually sends today.
TOTALS_FIELDS: tuple[str, ...] = (
    "blocks",
    "decisions",
    "gas_mon",
    "gas_usd",
    "jev_usd",
    "late_blocks",
    "pnl_mon",
    "pnl_pct",
    "pnl_usd",
    "realized_usd",
    "trades",
)

#: Ring buffer bound. The audit measured roughly 3.3 blocks/second (~300ms per
#: Monad block), so 600 events is about three minutes of history -- enough for
#: a reconnecting client to catch up without unbounded memory.
EVENT_BUFFER_SIZE = 600

#: Backoff between upstream reconnects: doubling from min to max, with jitter
#: so a fleet of restarts cannot stampede the upstream at the same instant.
BACKOFF_MIN_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 30.0

#: How long a subscriber waits for a new event before yielding a keepalive.
SUBSCRIBER_POLL_SECONDS = 1.0

#: A subscriber that cannot keep up is dropped rather than allowed to pin
#: memory; this caps how many events one subscriber may be handed per poll.
SUBSCRIBER_MAX_BATCH = 200


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _int_or_none(value: Any) -> int | None:
    parsed = _num(value)
    return int(parsed) if parsed is not None else None


def normalize_totals(raw: Any) -> dict[str, Any]:
    """Name the upstream totals, or refuse to publish a guess.

    The live feed sends an object with named keys, so that is the primary path
    and cannot suffer index drift. A list is still accepted defensively, but
    only when its length matches the audited layout exactly -- a reordered or
    extended array must surface as a schema mismatch rather than silently
    relabelling every statistic.

    Returns ``{"fields", "schema_mismatch", "length", "unknown_keys"?}``.
    """
    if isinstance(raw, dict):
        fields: dict[str, Any] = {}
        unknown: list[str] = []
        for key, value in raw.items():
            target = TOTALS_KEYS.get(str(key))
            if target is None:
                unknown.append(str(key))
            else:
                fields[target] = value
        # A missing key is not an error -- upstream may add or drop metrics --
        # but the caller needs to know the set was incomplete.
        return {
            "fields": fields,
            "schema_mismatch": False,
            "length": len(raw),
            "missing_keys": sorted(set(TOTALS_KEYS) - set(map(str, raw.keys()))),
            "unknown_keys": sorted(unknown),
        }
    if isinstance(raw, list):
        if len(raw) != len(TOTALS_FIELDS):
            return {
                "fields": {},
                "schema_mismatch": True,
                "length": len(raw),
                "raw": raw[: len(TOTALS_FIELDS) + 4],
            }
        return {
            "fields": {name: raw[index] for index, name in enumerate(TOTALS_FIELDS)},
            "schema_mismatch": False,
            "length": len(raw),
            "missing_keys": [],
            "unknown_keys": [],
        }
    return {"fields": {}, "schema_mismatch": raw is not None, "length": 0}


def normalize_event(raw: Any) -> dict[str, Any] | None:
    """Project one upstream block event onto the fields the UI consumes.

    Returns None for anything that is not a usable event, so a malformed line
    is dropped rather than rendered. Absent fields stay absent -- the UI is
    expected to show "unavailable" rather than a fabricated zero.
    """
    if not isinstance(raw, dict):
        return None
    block = _int_or_none(raw.get("block"))
    if block is None:
        return None

    decision_raw = raw.get("decision") if isinstance(raw.get("decision"), dict) else {}
    probabilities = (
        decision_raw.get("probabilities")
        if isinstance(decision_raw.get("probabilities"), dict)
        else {}
    )
    # Probabilities are not assumed complete, contiguous, or normalised: the
    # upstream sends whatever the model returned.
    probs = {
        str(k): _num(v)
        for k, v in probabilities.items()
        if _num(v) is not None
    }

    fill_raw = raw.get("fill") if isinstance(raw.get("fill"), dict) else None
    position_raw = raw.get("position") if isinstance(raw.get("position"), dict) else None

    return {
        "block": block,
        "ts": _int_or_none(raw.get("ts")),
        "mid": _num(raw.get("mid")),
        "best_bid": _num(raw.get("bestBid")),
        "best_ask": _num(raw.get("bestAsk")),
        "spread_bps": _num(raw.get("spreadBps")),
        "decision": {
            "action": decision_raw.get("action") if isinstance(decision_raw.get("action"), str) else None,
            "probabilities": probs,
            "up_in_10": _num(decision_raw.get("upIn10")),
            "latency_ms": _int_or_none(decision_raw.get("latencyMs")),
            # `late` means the model missed the block: the action is a
            # non-decision, which the UI must not present as a call.
            "late": bool(decision_raw.get("late")),
        },
        "fill": {
            "side": fill_raw.get("side"),
            "size": _num(fill_raw.get("size")),
            "price": _num(fill_raw.get("price")),
            # Kept as evidence, not decoration: `simulated` and a null txHash
            # are what tell the UI no real trade happened.
            "simulated": bool(fill_raw.get("simulated")),
            "tx_hash": fill_raw.get("txHash"),
            "gas_mon": _num(fill_raw.get("gasMon")),
        } if fill_raw else None,
        "has_position": position_raw is not None,
        "totals": normalize_totals(raw.get("totals")),
    }


def event_fingerprint(event: dict[str, Any]) -> str:
    """Stable identity for deduplication.

    The upstream block number is the natural key, but a block can legitimately
    carry more than one event, so the decision action is folded in. Timestamps
    alone are explicitly not used -- several valid events can share one.
    """
    decision = event.get("decision") or {}
    return f"{event.get('block')}:{decision.get('action')}:{event.get('ts')}"


class JevTraderIngestion:
    """One upstream connection, fanned out to many subscribers.

    Process-wide by design. The deployment runs a single api container (no
    compose `replicas`), so a module-level singleton is the correct scope; if
    that ever changes this must move behind a Redis leader lease, because two
    processes each opening a connection would double the upstream load and
    serve divergent buffers.
    """

    def __init__(self, url: str, *, enabled: bool = True) -> None:
        self.url = url.rstrip("/")
        self.enabled = enabled
        self._lock = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=EVENT_BUFFER_SIZE)
        self._seen: deque[str] = deque(maxlen=EVENT_BUFFER_SIZE * 2)
        self._seen_set: set[str] = set()
        self._seq = 0
        self._meta: dict[str, Any] = {}
        self._totals: dict[str, Any] = {"fields": {}, "schema_mismatch": False, "length": 0}
        self._connection = "idle"
        self._last_event_at: float | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None
        self._schema_mismatch = False
        self._thread: threading.Thread | None = None
        self._started = False

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Start the upstream reader once. Safe to call repeatedly."""
        if not self.enabled:
            self._connection = "disabled"
            return
        with self._lock:
            if self._started:
                return
            self._started = True
        self._thread = threading.Thread(
            target=self._run, name="jev-trader-ingest", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        backoff = BACKOFF_MIN_SECONDS
        while True:
            try:
                self._consume_once()
                backoff = BACKOFF_MIN_SECONDS      # a clean stream resets it
            except Exception as exc:               # never let the thread die
                self._last_error = f"{type(exc).__name__}: {exc}"[:300]
                logger.warning("jev-trader upstream error: %s", self._last_error)
            with self._lock:
                self._connection = "reconnecting"
            # Jitter keeps a restarting fleet from reconnecting in lockstep.
            time.sleep(backoff + random.uniform(0, backoff / 4))
            backoff = min(BACKOFF_MAX_SECONDS, backoff * 2)

    def _consume_once(self) -> None:
        timeout = httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)
        with httpx.Client(timeout=timeout) as client:
            with client.stream("GET", f"{self.url}/events") as response:
                response.raise_for_status()
                with self._lock:
                    self._connection = "connected"
                event_type = "message"
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if event_type == "snapshot":
                        self._apply_snapshot(payload)
                    elif event_type == "block":
                        self._apply_block(payload)
                    # Unknown event types (including any heartbeat) are
                    # ignored rather than guessed at.

    # --------------------------------------------------------------- ingest
    def _apply_snapshot(self, payload: str) -> None:
        try:
            body = json.loads(payload)
        except ValueError:
            return
        if not isinstance(body, dict):
            return
        with self._lock:
            self._meta = {
                "model": body.get("model"),
                "dry_run": body.get("dryRun"),
                "wallet": body.get("wallet"),
                "market": body.get("market"),
                "started_at": body.get("startedAt"),
            }
            self._last_success_at = time.time()
        history = body.get("history")
        if isinstance(history, list):
            # Snapshot history arrives oldest-first; the ring keeps the newest.
            for item in history[-EVENT_BUFFER_SIZE:]:
                self._apply_block_obj(item)

    def _apply_block(self, payload: str) -> None:
        try:
            self._apply_block_obj(json.loads(payload))
        except ValueError:
            return

    def _apply_block_obj(self, raw: Any) -> None:
        event = normalize_event(raw)
        if event is None:
            return
        fingerprint = event_fingerprint(event)
        with self._lock:
            if fingerprint in self._seen_set:
                return
            self._seen.append(fingerprint)
            self._seen_set.add(fingerprint)
            # Keep the dedup set bounded alongside its deque.
            while len(self._seen_set) > len(self._seen):
                self._seen_set.discard(self._seen.popleft())
            self._seq += 1
            event["seq"] = self._seq
            self._events.append(event)
            if event["totals"].get("schema_mismatch"):
                self._schema_mismatch = True
            if event["totals"].get("fields"):
                self._totals = event["totals"]
            self._last_event_at = time.time()
            self._last_success_at = self._last_event_at

    # ---------------------------------------------------------------- reads
    def _age_ms(self, at: float | None) -> int | None:
        return None if at is None else max(0, int((time.time() - at) * 1000))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest = self._events[-1] if self._events else None
            return {
                "schema_version": SCHEMA_VERSION,
                "meta": dict(self._meta),
                "latest": latest,
                "totals": dict(self._totals),
                "seq": self._seq,
                "buffer_size": len(self._events),
                "event_buffer_limit": EVENT_BUFFER_SIZE,
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            last_at = self._last_event_at
            return {
                "schema_version": SCHEMA_VERSION,
                # Connection and freshness are deliberately separate: the
                # stream can be open while the feed is simply quiet.
                "upstream_connection": self._connection,
                "last_event_at": last_at,
                "last_success_at": self._last_success_at,
                "event_age_ms": self._age_ms(last_at),
                "seq": self._seq,
                "buffer_size": len(self._events),
                "event_buffer_limit": EVENT_BUFFER_SIZE,
                "schema_mismatch": self._schema_mismatch,
                "ingestion_status": "ok" if self._connection == "connected" else self._connection,
                "last_error": self._last_error,
                "enabled": self.enabled,
            }

    def replay_from(self, since_seq: int) -> tuple[list[dict[str, Any]], bool]:
        """Events after *since_seq*, plus whether the gap is fully covered.

        The second element is False when the buffer has already rolled past the
        requested point, which is the signal that a caller must take a fresh
        snapshot instead of pretending it caught up.
        """
        with self._lock:
            if not self._events:
                return [], True
            oldest = self._events[0]["seq"]
            if since_seq + 1 < oldest:
                return [], False
            return [e for e in self._events if e["seq"] > since_seq], True

    def wait_for_events(self, since_seq: int, timeout: float) -> list[dict[str, Any]]:
        """Block up to *timeout* for events newer than *since_seq*."""
        deadline = time.time() + timeout
        while True:
            events, _ = self.replay_from(since_seq)
            if events:
                return events[:SUBSCRIBER_MAX_BATCH]
            if time.time() >= deadline:
                return []
            time.sleep(min(SUBSCRIBER_POLL_SECONDS, max(0.05, deadline - time.time())))

    def live_seq(self) -> int:
        with self._lock:
            return self._seq


_ingestion: JevTraderIngestion | None = None
_ingestion_lock = threading.Lock()


def get_ingestion() -> JevTraderIngestion:
    """Process-wide ingestion, started on first use."""
    global _ingestion
    settings = get_settings()
    with _ingestion_lock:
        if _ingestion is None:
            _ingestion = JevTraderIngestion(
                url=settings.jev_trader_feed_url,
                enabled=settings.jev_trader_enabled,
            )
        _ingestion.start()
        return _ingestion


def reset_ingestion() -> None:
    """Drop the singleton (tests / config reload)."""
    global _ingestion
    with _ingestion_lock:
        _ingestion = None


def subscribe(since_seq: int) -> Iterator[dict[str, Any]]:
    """Yield events for one subscriber, forever, without unbounded growth."""
    cursor = since_seq
    ingestion = get_ingestion()
    while True:
        events = ingestion.wait_for_events(cursor, SUBSCRIBER_POLL_SECONDS)
        if not events:
            yield {"type": "keepalive", "seq": cursor}
            continue
        for event in events:
            cursor = event["seq"]
            yield {"type": "event", "event": event}
