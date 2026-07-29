"""Backtest execution logger that publishes structured progress events
to Redis pub/sub so the frontend terminal window renders them in real time.

The channel ``backtest:logs:{run_id}`` is keyed per run and expires 30 min
after the final ``close`` event so completed-run logs are self-cleaning.
When Redis is unavailable the logger silently degrades (no-op) rather
than breaking the backtest.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class BacktestLogger:
    def __init__(self, run_id: str, redis_client: Any | None = None, ttl_seconds: int = 1800) -> None:
        self.run_id = run_id
        self.redis = redis_client
        self.channel = f"backtest:logs:{run_id}"
        self.ttl = ttl_seconds

    def _publish(self, event_type: str, **kwargs: Any) -> None:
        if self.redis is None:
            return
        payload = {"t": event_type, "ts": datetime.now(timezone.utc).isoformat(), **kwargs}
        try:
            self.redis.publish(self.channel, json.dumps(payload, default=str))
        except Exception:
            logger.debug("backtest_logger_publish_failed run_id=%s", self.run_id, exc_info=True)

    # ── lifecycle ──

    def start(self, assets: list[str], bars: int, engine: str, provider: str) -> None:
        self._publish("start", assets=assets, bars=bars, engine=engine, provider=provider,
                       line=f"[bold]▶ Starting {engine} backtest[/bold] — {', '.join(assets)} — {bars} bars from {provider}")

    def data_loaded(self, asset: str, bars: int, provider: str) -> None:
        self._publish("data", asset=asset, bars=bars, provider=provider,
                       line=f"  ✓ Loaded {bars} daily bars for {asset} ({provider})")

    def progress(self, bar: int, total: int, asset: str, close: float, equity: float) -> None:
        pct = round(bar / total * 100, 1)
        self._publish("progress", bar=bar, total=total, pct=pct, asset=asset,
                       close=round(close, 2), equity=round(equity, 2),
                       line=f"  [{pct:5.1f}%] bar {bar}/{total}  {asset} close=${close:,.2f}  equity=${equity:,.2f}")

    def trade(self, asset: str, ts: str, direction: str, price: float, position: float, equity: float) -> None:
        arrow = "↑" if direction == "buy" else "↓"
        self._publish("trade", asset=asset, ts=str(ts), direction=direction,
                       price=round(price, 4), position=round(position, 2), equity=round(equity, 2),
                       line=f"  {arrow} {direction.upper()} {asset} @ ${price:,.4f}  pos={position:.2f}  equity=${equity:,.2f}")

    def metric(self, name: str, value: float) -> None:
        self._publish("metric", name=name, value=round(value, 6),
                       line=f"  ∿ {name}: {value:.4f}")

    def complete(self, trades: int, final_equity: float, total_return: float, duration_ms: int) -> None:
        self._publish("complete", trades=trades, final_equity=round(final_equity, 2),
                       total_return=round(total_return, 6), duration_ms=duration_ms,
                       line=f"[bold][green]✓ Backtest finished[/green][/bold] — {trades} trades — "
                            f"return: {total_return * 100:.2f}% — final equity: ${final_equity:,.2f} — "
                            f"{duration_ms / 1000:.1f}s")

    def warning(self, message: str) -> None:
        self._publish("warning", line=f"[yellow]⚠ {message}[/yellow]")

    def error(self, message: str) -> None:
        self._publish("error", line=f"[red]✗ {message}[/red]")

    def close(self) -> None:
        self._publish("close", line="── stream ended (logs expire in 30 min) ──")
        if self.redis:
            try:
                self.redis.expire(self.channel, self.ttl)
            except Exception:
                pass
