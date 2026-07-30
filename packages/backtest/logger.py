"""Durable, Freqtrade-style event logging for a backtest run.

Each event is both published for low-latency delivery and appended to a
bounded Redis list.  Pub/Sub alone is deliberately not used as the source of
truth: a browser can subscribe after the worker has started (or reconnect)
and must still receive the terminal transcript.  The list and its sequence
counter expire after the configurable retention period.

Logging is observability only.  A Redis failure must never fail or slow down
the financial calculation, so every Redis operation is best-effort.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30 * 60
DEFAULT_MAX_EVENTS = 2_000


def _terminal_text(value: object, *, limit: int = 300) -> str:
    """Keep a log event to one safe, readable terminal line."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    return " ".join(text.split())[:limit]


class BacktestLogger:
    """Publish and retain structured terminal events for one run."""

    def __init__(
        self,
        run_id: str,
        redis_client: Any | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        self.run_id = run_id
        self.redis = redis_client
        self.channel = f"backtest:logs:{run_id}"
        self.history_key = f"{self.channel}:history"
        self.sequence_key = f"{self.channel}:sequence"
        self.ttl = ttl_seconds
        self.max_events = max(1, max_events)
        self._closed = False

    def _publish(self, event_type: str, **kwargs: Any) -> None:
        if self.redis is None:
            return
        try:
            # The sequence is allocated before the payload is persisted.  The
            # SSE endpoint uses it to de-duplicate Pub/Sub events that arrive
            # while it is replaying the retained history.
            sequence = int(self.redis.incr(self.sequence_key))
            payload = {
                "t": event_type,
                "ts": datetime.now(timezone.utc).isoformat(),
                "seq": sequence,
                **kwargs,
            }
            raw = json.dumps(payload, default=str, separators=(",", ":"))
            pipeline = self.redis.pipeline(transaction=True)
            pipeline.rpush(self.history_key, raw)
            pipeline.ltrim(self.history_key, -self.max_events, -1)
            pipeline.expire(self.history_key, self.ttl)
            pipeline.expire(self.sequence_key, self.ttl)
            pipeline.publish(self.channel, raw)
            pipeline.execute()
        except Exception:
            logger.debug("backtest_logger_publish_failed run_id=%s", self.run_id, exc_info=True)
            # Do not let a Redis outage turn each subsequent trade/progress
            # event into another socket timeout on the calculation worker.
            self.redis = None

    # ── lifecycle ──

    def start(self, assets: list[str], bars: int, engine: str, provider: str) -> None:
        self._publish(
            "start",
            assets=assets,
            bars=bars,
            engine=engine,
            provider=provider,
            line=f"▶ Starting {engine} backtest — {', '.join(assets)} — {bars} bars from {provider}",
        )

    def data_loaded(self, asset: str, bars: int, provider: str) -> None:
        self._publish(
            "data",
            asset=asset,
            bars=bars,
            provider=provider,
            line=f"  ✓ Loaded {bars} daily bars for {asset} ({provider})",
        )

    def progress(self, bar: int, total: int, asset: str, close: float, equity: float) -> None:
        total = max(1, total)
        completed = min(max(bar, 0), total)
        pct = round(completed / total * 100, 1)
        filled = min(20, round(pct / 5))
        bar_graph = "█" * filled + "░" * (20 - filled)
        self._publish(
            "progress",
            bar=completed,
            total=total,
            pct=pct,
            asset=asset,
            close=round(close, 2),
            equity=round(equity, 2),
            line=f"  [{bar_graph}] {pct:5.1f}%  bar {completed}/{total}  {asset} close=${close:,.2f}  equity=${equity:,.2f}",
        )

    def trade(self, asset: str, bar_ts: str, direction: str, price: float, position: float, equity: float) -> None:
        arrow = "↑" if direction == "buy" else "↓"
        self._publish(
            "trade",
            asset=asset,
            bar_ts=str(bar_ts),
            direction=direction,
            price=round(price, 4),
            position=round(position, 2),
            equity=round(equity, 2),
            line=f"  {arrow} {direction.upper()} {asset} @ ${price:,.4f}  pos={position:.2f}  equity=${equity:,.2f}",
        )

    def metric(self, name: str, value: float) -> None:
        self._publish(
            "metric",
            name=_terminal_text(name, limit=80),
            value=round(value, 6),
            line=f"  ∿ {_terminal_text(name, limit=80)}: {value:.4f}",
        )

    def complete(self, trades: int, final_equity: float, total_return: float, duration_ms: int) -> None:
        self._publish(
            "complete",
            trades=trades,
            final_equity=round(final_equity, 2),
            total_return=round(total_return, 6),
            duration_ms=duration_ms,
            line=(
                f"✓ Backtest finished — {trades} trades — return: {total_return * 100:.2f}% — "
                f"final equity: ${final_equity:,.2f} — {duration_ms / 1000:.1f}s"
            ),
        )

    def warning(self, message: str) -> None:
        self._publish("warning", line=f"⚠ {_terminal_text(message)}")

    def error(self, message: str) -> None:
        self._publish("error", line=f"✗ {_terminal_text(message)}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._publish("close", line="── stream ended (logs expire in 30 min) ──")
