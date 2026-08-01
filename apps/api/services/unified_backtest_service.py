from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import update
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
from packages.database.models import BacktestArtifact, BacktestRun, StrategyVersion, TradingStrategy

logger = logging.getLogger(__name__)
BACKTEST_CREDITS = 50
EXPORT_CREDITS = 50
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
LOOKAHEAD_GUARD = "signals executed on next bar close"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _spec_payload(spec: dict, window_days: int) -> dict:
    return {"spec": spec, "window_days": window_days, "engine": "vectorbt", "version": 1}


def _base_assumptions(spec: dict) -> dict:
    return {
        "fee_bps": float(spec.get("fee_bps", 10.0)),
        "slippage_bps": float(spec.get("slippage_bps", 0.0)),
        "sample_start": None,
        "sample_end": None,
        "benchmark": "equal_weight_buy_hold",
        "data_source": "pending",
        "interval": "1d",
        "lookahead_guard": LOOKAHEAD_GUARD,
        "live_trading": False,
    }


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
        assumptions_json=_base_assumptions(spec),
        credits_reserved=reservation.credits,
        credits_spent=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def queue_unified_run(db: Session, run_id: str) -> str:
    """Hand a queued run to the Celery worker; inline only outside production.

    Returns ``"celery"`` or ``"inline"``. Raises RuntimeError in production
    when the queue is unavailable (the run is failed + refunded first).
    """
    try:
        from apps.api.redis_client import get_redis
        get_redis().ping()
        from packages.workers.tasks import execute_unified_backtest
        execute_unified_backtest.delay(run_id)
        return "celery"
    except Exception as exc:
        from apps.api.config import get_settings
        if get_settings().app_environment.lower() == "production":
            fail_unified_run(db, run_id, code="BACKTEST_QUEUE_UNAVAILABLE", message=str(exc))
            raise RuntimeError("Backtest queue is temporarily unavailable") from exc
        execute_unified_run(db, run_id)
        return "inline"


def _build_window(db: Session, spec: dict, start: datetime, end: datetime) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Load the candle window per asset. Crypto comes from the shared Binance
    store, US equities from the keyed provider chain. Synthetic data is only
    allowed outside production (explicitly guarded)."""
    assets = [str(item).upper() for item in spec["assets"]]
    crypto_assets = [asset for asset in assets if is_crypto_asset(asset)]
    equity_assets = [asset for asset in assets if asset not in crypto_assets]
    window: dict[str, list[dict]] = {}
    sources: dict[str, str] = {}
    if crypto_assets:
        freshness = "binance"
        try:
            refresh_daily_candles(db, crypto_assets)
        except Exception:
            assert_synthetic_allowed("unified backtest synthetic candle fallback")
            freshness = "mock"
            now = _now()
            window = {
                asset: [{"ts": now - timedelta(days=365 - index), "close": 100 + index * 0.15 + ((index % 11) - 5) * 0.4} for index in range(365)]
                for asset in crypto_assets
            }
        if freshness == "binance":
            window.update(load_candle_window(db, crypto_assets, start, end))
            sources.update({asset: provider_for_asset(asset) for asset in crypto_assets})
        else:
            sources.update({asset: freshness for asset in crypto_assets})
    if equity_assets:
        loader = EquityDailyLoader()
        for asset in equity_assets:
            window[asset] = loader.load_daily(asset, start, end)
            sources[asset] = "equity:" + ("+".join(loader.configured_providers) or "unavailable")
    return window, sources


def execute_unified_run(db: Session, run_id: str) -> BacktestRun:
    row = db.get(BacktestRun, run_id)
    if not row:
        raise ValueError("Backtest run not found")
    if row.status in TERMINAL_STATUSES:
        return row
    reservation_key = f"backtest-charge:{row.idempotency_key}"
    reservation = CreditReservation(idempotency_key=reservation_key, credits=row.credits_reserved or BACKTEST_CREDITS)
    row.status = "running"
    db.commit()
    backtest_logger: BacktestLogger | None = None
    try:
        spec = parse_spec((row.spec_json or {}).get("spec") or row.params_json).model_dump()
        window_days = int((row.spec_json or {}).get("window_days", 30))
        end = _now()
        start = end - timedelta(days=max(1, min(window_days, 30)))
        window, sources = _build_window(db, spec, start, end)
        data_source = "+".join(sorted({source.split(":")[0] for source in sources.values()}))
        try:
            # Publishing is intentionally best effort: a Redis outage must not
            # change the paid backtest outcome.
            backtest_logger = BacktestLogger(row.id, get_redis())
            backtest_logger.start(
                spec["assets"],
                sum(len(window.get(asset, [])) for asset in spec["assets"]),
                "vectorbt",
                data_source or "store",
            )
        except Exception:
            logger.warning("backtest_terminal_logger_unavailable run_id=%s", run_id, exc_info=True)
            backtest_logger = None
        result = run_vectorbt({**spec, "data_sources": sources}, window, logger=backtest_logger)
        # The user may have cancelled while the engine was running; the cancel
        # path already refunded the reservation. Never overwrite or settle.
        db.expire_all()
        row = db.get(BacktestRun, run_id)
        if row.status == "cancelled":
            if backtest_logger:
                backtest_logger.close()
            db.commit()
            db.refresh(row)
            return row
        coverage = candle_coverage(db)
        result["data_freshness"] = data_source
        result["data_sources"] = sources
        result["bar_count"] = sum(len(window.get(asset, [])) for asset in spec["assets"])
        result["requested_engine"] = "vectorbt"
        snapshot = {"provider": data_source, "providers": sources, "interval": "1d", "coverage": coverage, "bar_count": result["bar_count"], "window_start": start.isoformat(), "window_end": end.isoformat()}
        assumptions = {
            **_base_assumptions(spec),
            "sample_start": start.isoformat(),
            "sample_end": end.isoformat(),
            "data_source": data_source,
            "data_sources": sources,
        }
        # Finalize with a consistent lock order (run row first, then the credit
        # reservation — the same order cancel uses) so a concurrent cancel can
        # never deadlock or be clobbered. The re-asserting update acquires the
        # row lock and proves the run is still ``running``.
        locked = db.execute(
            update(BacktestRun)
            .where(BacktestRun.id == run_id, BacktestRun.status == "running")
            .values(status="running")
        ).rowcount
        if not locked:
            db.rollback()
            row = db.get(BacktestRun, run_id)
            if backtest_logger:
                backtest_logger.close()
            return row
        settlement = settle_task(db, row.user_id, reservation, BACKTEST_CREDITS, {"engine": "vectorbt", "backtest_id": row.id})
        db.execute(
            update(BacktestRun)
            .where(BacktestRun.id == run_id, BacktestRun.status == "running")
            .values(
                result_json=result,
                data_snapshot_json=snapshot,
                assumptions_json=assumptions,
                credits_spent=settlement.actual,
                status="completed",
                completed_at=_now(),
            )
        )
        db.commit()
        if backtest_logger:
            backtest_logger.close()
        db.expire_all()
        row = db.get(BacktestRun, run_id)
    except Exception as exc:
        logger.exception("unified_backtest_execution_failed run_id=%s", run_id)
        if backtest_logger:
            # The terminal is customer-facing; keep infrastructure details in
            # server logs and offer only the safe operational outcome here.
            backtest_logger.error("Backtest failed. Credits will be refunded automatically.")
            backtest_logger.close()
        db.rollback()
        row = db.get(BacktestRun, run_id)
        row.status = "failed"
        error: dict[str, Any] = {"message": str(exc)[:500], "type": type(exc).__name__}
        if getattr(exc, "code", None):
            error["code"] = exc.code
        if isinstance(exc, EquityDataUnavailable):
            error["reasons"] = exc.reasons
        row.error_json = error
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
    if not row or row.status in TERMINAL_STATUSES:
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


def cancel_unified_run(db: Session, user_id: str, run_id: str) -> BacktestRun:
    """Cancel a queued/running run and refund the reservation. Idempotent.

    The state flip is an atomic conditional UPDATE so a worker that is about
    to mark the run completed cannot clobber a concurrent cancellation.
    """
    row = db.query(BacktestRun).filter_by(id=run_id, user_id=user_id).one_or_none()
    if not row:
        raise ValueError("Backtest run not found")
    if row.status == "cancelled":
        return row
    if row.status in {"completed", "failed"}:
        raise ValueError(f"cannot cancel a {row.status} backtest run")
    reservation = CreditReservation(
        idempotency_key=f"backtest-charge:{row.idempotency_key}",
        credits=row.credits_reserved or BACKTEST_CREDITS,
    )
    updated = db.execute(
        update(BacktestRun)
        .where(BacktestRun.id == run_id, BacktestRun.status.in_(["queued", "running"]))
        .values(
            status="cancelled",
            error_json={"code": "CANCELLED_BY_USER", "message": "Backtest run cancelled by user"},
            completed_at=_now(),
        )
    ).rowcount
    if not updated:
        db.expire_all()
        row = db.get(BacktestRun, run_id)
        if row.status == "cancelled":
            return row
        raise ValueError(f"cannot cancel a {row.status} backtest run")
    try:
        refund_task(db, user_id, reservation, "BACKTEST_CANCELLED_BY_USER")
    except Exception:
        logger.exception("backtest_cancel_refund_failed run_id=%s", run_id)
    db.commit()
    db.expire_all()
    row = db.get(BacktestRun, run_id)
    return row


def save_run_as_strategy(db: Session, user_id: str, run_id: str) -> dict:
    """Create a DRAFT/PAPER TradingStrategy + StrategyVersion from a completed
    run's spec. Idempotent per run: repeated calls return the same strategy."""
    row = db.query(BacktestRun).filter_by(id=run_id, user_id=user_id).one_or_none()
    if not row:
        raise ValueError("Backtest run not found")
    if row.status != "completed":
        raise ValueError("only completed backtest runs can be saved as a strategy")
    if row.strategy_id:
        strategy = db.get(TradingStrategy, row.strategy_id)
        if strategy:
            version = db.query(StrategyVersion).filter_by(strategy_id=strategy.id, version=strategy.current_version).one_or_none()
            return {"strategy": strategy, "version": version, "created": False}
    spec = parse_spec((row.spec_json or {}).get("spec") or row.params_json).model_dump()
    draft = {
        "source": "backtest_run",
        "run_id": row.id,
        "engine": row.engine,
        "spec": spec,
        "assumptions": row.assumptions_json or {},
        "interval": "1d",
    }
    config_hash = hashlib.sha256(json.dumps(draft, sort_keys=True, default=str).encode()).hexdigest()
    strategy = TradingStrategy(
        user_id=user_id,
        name=row.strategy_name[:120],
        description=(spec.get("thesis") or f"Saved from research backtest run {row.id}")[:2000],
        status="DRAFT",
        current_version=1,
        execution_mode="PAPER",
    )
    db.add(strategy)
    db.flush()
    version = StrategyVersion(
        user_id=user_id,
        strategy_id=strategy.id,
        version=1,
        draft_json=draft,
        config_hash=config_hash,
        status="DRAFT",
        created_by=user_id,
    )
    db.add(version)
    row.strategy_id = strategy.id
    row.strategy_version = "1"
    db.commit()
    db.refresh(strategy)
    db.refresh(version)
    return {"strategy": strategy, "version": version, "created": True}


def serialize_saved_strategy(payload: dict) -> dict:
    strategy = payload["strategy"]
    version = payload.get("version")
    return {
        "id": strategy.id,
        "name": strategy.name,
        "status": strategy.status,
        "execution_mode": strategy.execution_mode,
        "current_version": strategy.current_version,
        "created": bool(payload.get("created")),
        "version": {
            "id": version.id,
            "strategy_id": version.strategy_id,
            "version": version.version,
            "status": version.status,
            "config_hash": version.config_hash,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }
        if version
        else None,
    }


def serialize_unified_run(row: BacktestRun, artifacts: list[BacktestArtifact] | None = None) -> dict:
    result = row.result_json or {}
    spec = row.spec_json or {}
    return {"id": row.id, "status": row.status, "engine": row.engine, "mode": (spec.get("spec") or {}).get("mode", "daily"), "strategy_name": row.strategy_name, "asset": row.asset, "spec": spec.get("spec", spec), "run_spec": spec, "window": {"start": (row.data_snapshot_json or {}).get("window_start"), "end": (row.data_snapshot_json or {}).get("window_end")}, "params": row.params_json, "result": result, "performance": result.get("metrics", {}), "equity_curve": result.get("equity_curve", []), "drawdown_curve": result.get("drawdown_curve", []), "benchmark_curve": result.get("benchmark_curve", []), "trades": result.get("trades", []), "positions": result.get("positions", []), "charts": result.get("charts", {}), "data_snapshot": row.data_snapshot_json or {}, "assumptions": row.assumptions_json or {}, "error": row.error_json or {}, "strategy_id": row.strategy_id, "credits_spent": row.credits_spent, "credits_reserved": row.credits_reserved, "artifacts": [serialize_artifact(item) for item in artifacts] if artifacts is not None else [], "created_at": row.created_at.isoformat() if row.created_at else None, "completed_at": row.completed_at.isoformat() if row.completed_at else None}


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
