from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.entitlement_service import assert_action_allowed
from apps.api.redis_client import get_redis
from packages.backtest.artifacts import artifact_path, write_json_artifact
from packages.backtest.daily_data import candle_coverage, is_crypto_asset, load_candle_window, provider_for_asset, refresh_daily_candles
from packages.backtest.engines import assert_synthetic_allowed
from packages.backtest.equity_daily import EquityDailyLoader, EquityDataUnavailable
from packages.backtest.logger import BacktestLogger
from packages.backtest.strategy_spec import parse_spec
from packages.backtest.vectorbt_engine import run_vectorbt
from packages.billing.metering import CreditReservation
from packages.database.models import BacktestArtifact, BacktestRun

logger = logging.getLogger(__name__)
BACKTEST_CREDITS = 50
EXPORT_CREDITS = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _spec_payload(spec: dict, window_days: int) -> dict:
    return {"spec": spec, "window_days": window_days, "engine": "vectorbt", "version": 1}


def create_unified_run(db: Session, user_id: str, spec_payload: dict, *, window_days: int, idempotency_key: str | None = None, context_meta: dict | None = None) -> BacktestRun:
    assert_action_allowed(db, user_id, "backtest")
    key = f"unified-backtest:{user_id}:{idempotency_key or os.urandom(8).hex()}"
    existing = db.query(BacktestRun).filter_by(idempotency_key=key).one_or_none()
    if existing:
        return existing
    spec = parse_spec(spec_payload).model_dump()
    quote = quote_task(task_type="backtest", requested_model="default", async_execution=True)
    reservation = reserve_task(db, user_id, quote, f"backtest-charge:{key}", {"engine": "vectorbt", "assets": spec["assets"]})
    row = BacktestRun(
        user_id=user_id,
        idempotency_key=key,
        status="queued",
        engine="vectorbt",
        strategy_name=spec["name"],
        asset=spec["assets"][0],
        params_json=spec,
        spec_json={**_spec_payload(spec, window_days), "context_meta": context_meta or {}},
        assumptions_json={"execution": "next-bar close-to-close", "fees": "fee_bps per turnover", "lookahead": False, "live_trading": False},
        credits_reserved=reservation.credits,
        credits_spent=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def execute_unified_run(db: Session, run_id: str) -> BacktestRun:
    row = db.get(BacktestRun, run_id)
    if not row:
        raise ValueError("Backtest run not found")
    if row.status in {"completed", "failed"}:
        return row
    reservation_key = f"backtest-charge:{row.idempotency_key}"
    reservation = CreditReservation(idempotency_key=reservation_key, credits=row.credits_reserved or BACKTEST_CREDITS)
    row.status = "running"
    db.commit()
    bl: BacktestLogger | None = None
    try:
        spec = parse_spec((row.spec_json or {}).get("spec") or row.params_json).model_dump()
        window_days = int((row.spec_json or {}).get("window_days", 365 * 3))
        freshness = "binance"
        try:
            refresh_daily_candles(db, spec["assets"])
        except Exception:
            from apps.api.config import get_settings
            if get_settings().app_environment.lower() == "production":
                raise
            freshness = "mock"
            from datetime import timedelta
            now = _now()
            window = {asset: [{"ts": now - timedelta(days=365 - index), "close": 100 + index * 0.15 + ((index % 11) - 5) * 0.4} for index in range(365)] for asset in spec["assets"]}
        else:
            window = None
        end = _now()
        from datetime import timedelta
        start = end - timedelta(days=max(30, min(window_days, 365 * 3)))
        if window is None:
            window = load_candle_window(db, spec["assets"], start, end)
        # Real-time terminal logger (Redis pub/sub → SSE).  Degrades
        # silently when Redis is unavailable (no-op logger).
        bl: BacktestLogger | None = None
        try:
            redis = get_redis()
            redis.ping()
            bl = BacktestLogger(row.id, redis)
            bl.start(spec["assets"], sum(len(window.get(asset, [])) for asset in spec["assets"]),
                     "vectorbt", freshness)
        except Exception:
            pass
        result = run_vectorbt(spec, window, logger=bl)
        if bl:
            bl.close()
        coverage = candle_coverage(db)
        result["data_freshness"] = freshness
        result["bar_count"] = sum(len(window.get(asset, [])) for asset in spec["assets"])
        result["disclaimer"] = "Hypothetical research backtest. Past performance does not predict future results. Users bear all risks of using this service."
        result["requested_engine"] = "vectorbt"
        row.result_json = result
        row.data_snapshot_json = {"provider": freshness, "interval": "1d", "coverage": coverage, "bar_count": result["bar_count"], "window_start": start.isoformat(), "window_end": end.isoformat()}
        settlement = settle_task(db, row.user_id, reservation, BACKTEST_CREDITS, {"engine": "vectorbt", "backtest_id": row.id})
        row.credits_spent = settlement.actual
        row.status = "completed"
        row.completed_at = _now()
        db.commit()
    except Exception as exc:
        if bl:
            bl.error(str(exc)[:300])
            bl.close()
        db.rollback()
        row = db.get(BacktestRun, run_id)
        row.status = "failed"
        row.error_json = {"message": str(exc)[:500], "type": type(exc).__name__}
        try:
            refund_task(db, row.user_id, reservation, "BACKTEST_EXECUTION_FAILED")
        except Exception:
            logger.exception("backtest_refund_failed run_id=%s", run_id)
        db.commit()
        raise
    return row


def fail_unified_run(db: Session, run_id: str, *, code: str, message: str) -> BacktestRun | None:
    """Fail and refund a queued run that could not be handed to a worker."""
    row = db.get(BacktestRun, run_id)
    if not row or row.status in {"completed", "failed"}:
        return row
    reservation = CreditReservation(
        idempotency_key=f"backtest-charge:{row.idempotency_key}",
        credits=row.credits_reserved or BACKTEST_CREDITS,
    )
    row.status = "failed"
    row.error_json = {"code": code, "message": message[:500]}
    try:
        refund_task(db, row.user_id, reservation, code)
    except Exception:
        logger.exception("backtest_refund_failed run_id=%s", run_id)
    db.commit()
    db.refresh(row)
    return row


def serialize_unified_run(row: BacktestRun) -> dict:
    result = row.result_json or {}
    spec = row.spec_json or {}
    return {"id": row.id, "status": row.status, "engine": row.engine, "mode": (spec.get("spec") or {}).get("mode", "daily"), "strategy_name": row.strategy_name, "asset": row.asset, "spec": spec.get("spec", spec), "run_spec": spec, "window": {"start": (row.data_snapshot_json or {}).get("window_start"), "end": (row.data_snapshot_json or {}).get("window_end")}, "params": row.params_json, "result": result, "performance": result.get("metrics", {}), "equity_curve": result.get("equity_curve", []), "drawdown_curve": result.get("drawdown_curve", []), "benchmark_curve": result.get("benchmark_curve", []), "trades": result.get("trades", []), "positions": result.get("positions", []), "charts": result.get("charts", {}), "data_snapshot": row.data_snapshot_json or {}, "assumptions": row.assumptions_json or {}, "error": row.error_json or {}, "credits_spent": row.credits_spent, "credits_reserved": row.credits_reserved, "created_at": row.created_at.isoformat() if row.created_at else None, "completed_at": row.completed_at.isoformat() if row.completed_at else None}


def export_run(db: Session, user_id: str, run_id: str, fmt: str = "json") -> BacktestArtifact:
    assert_action_allowed(db, user_id, "backtest")
    row = db.query(BacktestRun).filter_by(id=run_id, user_id=user_id).one_or_none()
    if not row:
        raise ValueError("Backtest run not found")
    if row.status != "completed":
        raise ValueError("Backtest run is not completed")
    fmt = fmt.lower().strip()
    if fmt not in {"json", "csv"}:
        raise ValueError("unsupported export format")
    quote = quote_task(task_type="backtest_export", requested_model="default", async_execution=False)
    reservation = reserve_task(db, user_id, quote, f"backtest-export:{run_id}:{fmt}", {"backtest_id": run_id, "format": fmt})
    db.commit()
    try:
        payload = serialize_unified_run(row)
        if fmt == "json":
            meta = write_json_artifact(user_id, run_id, "report", payload)
            artifact_type = "report"
        else:
            relative = Path(user_id) / run_id / "trades.csv"
            path = artifact_path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            buf = io.StringIO()
            trades = payload["trades"]
            writer = csv.DictWriter(buf, fieldnames=sorted({key for item in trades for key in item} or {"ts"}))
            writer.writeheader()
            writer.writerows(trades)
            raw = buf.getvalue().encode("utf-8")
            path.write_bytes(raw)
            import hashlib
            meta = {"relative_path": relative.as_posix(), "size_bytes": len(raw), "checksum": hashlib.sha256(raw).hexdigest(), "format": "csv"}
            artifact_type = "trades"
        settlement = settle_task(db, user_id, reservation, EXPORT_CREDITS, {"backtest_id": run_id, "format": fmt})
        artifact = BacktestArtifact(user_id=user_id, backtest_id=run_id, artifact_type=artifact_type, format=fmt, relative_path=meta["relative_path"], size_bytes=meta["size_bytes"], checksum=meta["checksum"], credits_spent=settlement.actual)
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact
    except Exception:
        db.rollback()
        refund_task(db, user_id, reservation, "BACKTEST_EXPORT_FAILED")
        db.commit()
        raise


def serialize_artifact(artifact: BacktestArtifact) -> dict:
    return {"id": artifact.id, "backtest_id": artifact.backtest_id, "artifact_type": artifact.artifact_type, "format": artifact.format, "relative_path": artifact.relative_path, "size_bytes": artifact.size_bytes, "checksum": artifact.checksum, "credits_spent": artifact.credits_spent, "created_at": artifact.created_at.isoformat() if artifact.created_at else None}
