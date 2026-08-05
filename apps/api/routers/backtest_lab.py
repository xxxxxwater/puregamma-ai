from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.config import get_settings
from apps.api.services.backtest_lab_service import (
    generate_lab_spec,
    lab_status,
    serialize_lab_run,
)
from apps.api.services.unified_backtest_service import (
    create_unified_run,
    export_run,
    fail_unified_run,
    serialize_artifact,
    serialize_unified_run,
)
from packages.backtest.artifacts import artifact_root
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from packages.backtest.daily_data import LAB_SYMBOLS, refresh_daily_candles
from packages.database.models import BacktestArtifact, BacktestLabRun, BacktestRun, User
from apps.api.redis_client import get_redis

router = APIRouter(prefix="/backtest-lab", tags=["backtest-lab"])


class BacktestDispatchUnavailable(RuntimeError):
    pass


class GenerateSpecRequest(BaseModel):
    idea: str = Field(default="", max_length=2000)
    use_memory: bool = True
    locale: str = "en"


class RunLabRequest(BaseModel):
    spec: dict
    window_days: int = Field(default=30, ge=1, le=30)
    idempotency_key: str | None = Field(default=None, max_length=120)
    context_meta: dict = Field(default_factory=dict)


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"symbols": sorted(LAB_SYMBOLS), **lab_status(db)}


@router.post("/generate-spec")
def generate_spec(payload: GenerateSpecRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    locale = "zh" if payload.locale == "zh" else "en"
    spec, meta = generate_lab_spec(db, user.id, payload.idea, use_memory=payload.use_memory, locale=locale)
    return {"spec": spec.model_dump(), "meta": meta}


@router.post("/runs")
def create_run(payload: RunLabRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = create_unified_run(db, user.id, payload.spec, window_days=payload.window_days, idempotency_key=payload.idempotency_key, context_meta=payload.context_meta)
        _dispatch_or_run(db, row.id)
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except BacktestDispatchUnavailable as exc:
        raise HTTPException(status_code=503, detail={"code": "BACKTEST_QUEUE_UNAVAILABLE", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(row)
    return {"run": serialize_unified_run(row)}


@router.get("/runs")
def runs(limit: int = 20, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    requested_limit = min(limit, 50)
    requested_offset = max(0, offset)
    unified = [serialize_unified_run(row) for row in db.query(BacktestRun).filter_by(user_id=user.id).order_by(BacktestRun.created_at.desc()).offset(requested_offset).limit(requested_limit).all()]
    legacy = []
    if requested_offset == 0:
        for row in db.query(BacktestLabRun).filter_by(user_id=user.id).order_by(BacktestLabRun.created_at.desc()).limit(requested_limit).all():
            payload = serialize_lab_run(row)
            payload.update({"engine": "legacy_backtest_lab", "run_spec": {"legacy": True}, "drawdown_curve": [], "benchmark_curve": [], "trades": [], "positions": [], "charts": {}, "error": {"message": row.error} if row.error else {}, "credits_reserved": 0, "completed_at": row.updated_at.isoformat() if row.updated_at else None, "is_legacy": True})
            legacy.append(payload)
    merged = sorted([*unified, *legacy], key=lambda item: item.get("created_at") or "", reverse=True)[:requested_limit]
    return {"runs": merged, "limit": requested_limit, "offset": requested_offset}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(BacktestRun, run_id)
    if row and row.user_id == user.id:
        artifacts = db.query(BacktestArtifact).filter_by(backtest_id=row.id, user_id=user.id).order_by(BacktestArtifact.created_at.asc()).all()
        return {"run": serialize_unified_run(row, artifacts=artifacts)}
    legacy = db.get(BacktestLabRun, run_id)
    if not legacy or legacy.user_id != user.id:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    payload = serialize_lab_run(legacy)
    payload.update({"engine": "legacy_backtest_lab", "run_spec": {"legacy": True}, "drawdown_curve": [], "benchmark_curve": [], "trades": [], "positions": [], "charts": {}, "error": {"message": legacy.error} if legacy.error else {}, "credits_reserved": 0, "completed_at": legacy.updated_at.isoformat() if legacy.updated_at else None, "is_legacy": True})
    return {"run": payload}


def _dispatch_or_run(db: Session, run_id: str) -> None:
    """Prefer Celery/Redis, while keeping local development deterministic."""
    try:
        from apps.api.redis_client import get_redis
        get_redis().ping()
        from packages.workers.tasks import execute_unified_backtest
        execute_unified_backtest.delay(run_id)
        return
    except Exception as exc:
        if get_settings().app_environment.lower() == "production":
            fail_unified_run(db, run_id, code="BACKTEST_QUEUE_UNAVAILABLE", message=str(exc))
            raise BacktestDispatchUnavailable("Backtest queue is temporarily unavailable") from exc
        # Local/test environments commonly do not run Redis. The same worker
        # function is invoked inline so the API contract remains usable.
        from apps.api.services.unified_backtest_service import execute_unified_run
        execute_unified_run(db, run_id)


@router.post("/runs/{run_id}/export")
def export_backtest(run_id: str, format: str = "json", db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return {"artifact": serialize_artifact(export_run(db, user.id, run_id, format))}
    except (ValueError, InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402 if isinstance(exc, (InsufficientCreditsError, EntitlementDeniedError)) else 400, detail=str(exc)) from exc


@router.get("/artifacts/{artifact_id}")
def download_artifact(artifact_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = db.query(BacktestArtifact).filter_by(id=artifact_id, user_id=user.id).one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    root = artifact_root()
    path = (root / artifact.relative_path).resolve()
    if root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(path, media_type="application/json" if artifact.format == "json" else "text/csv", filename=path.name)


@router.post("/data/refresh")
def refresh_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    stats = refresh_daily_candles(db, list(LAB_SYMBOLS))
    return {"stats": stats, **lab_status(db)}


def _decode_terminal_event(raw: object) -> dict | None:
    """Decode one retained Redis event without letting malformed data kill SSE."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(str(raw))
        return payload if isinstance(payload, dict) else None
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _event_sequence(payload: dict) -> int:
    try:
        return int(payload.get("seq", 0))
    except (TypeError, ValueError):
        return 0


def _sse_event(payload: dict) -> str:
    """Render a safe SSE message and expose its sequence for reconnection."""
    sequence = _event_sequence(payload)
    event_id = f"id: {sequence}\n" if sequence else ""
    return f"{event_id}event: message\ndata: {json.dumps(payload, default=str, separators=(',', ':'))}\n\n"


@router.get("/runs/{run_id}/stream")
def stream_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Replay and stream an authenticated run's terminal events over SSE."""
    row = db.get(BacktestRun, run_id)
    if not row or row.user_id != user.id:
        # Do not reveal whether an arbitrary UUID exists for a different user.
        raise HTTPException(status_code=404, detail="Backtest run not found")

    channel = f"backtest:logs:{run_id}"
    history_key = f"{channel}:history"
    try:
        last_sequence = max(0, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        last_sequence = 0

    def event_generator():
        nonlocal last_sequence
        try:
            redis = get_redis()
            redis.ping()
        except Exception:
            yield _sse_event({"t": "error", "line": "Redis unavailable — terminal output disabled"})
            yield _sse_event({"t": "close", "line": "── stream unavailable ──"})
            return

        # Subscribe first, then replay persisted events.  The logger writes to
        # the list before publishing, so any event emitted in this small race
        # is either in the replay or queued by Pub/Sub; `seq` de-duplicates it.
        pubsub = redis.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(channel)
            history = redis.lrange(history_key, 0, -1)
            replayed_any = False
            for raw in history:
                payload = _decode_terminal_event(raw)
                if payload is None:
                    continue
                sequence = _event_sequence(payload)
                if sequence and sequence <= last_sequence:
                    continue
                if sequence:
                    last_sequence = sequence
                replayed_any = True
                yield _sse_event(payload)
                if payload.get("t") == "close":
                    return

            # A completed historic run may legitimately have outlived its
            # retained transcript.  Finish immediately instead of holding an
            # EventSource open forever.
            if row.status in {"completed", "failed", "cancelled"} and not replayed_any:
                yield _sse_event({"t": "close", "line": "── terminal transcript is no longer available ──"})
                return

            idle_polls = 0
            while True:
                msg = pubsub.get_message(timeout=2.0)
                if msg is None:
                    idle_polls += 1
                    # A worker can fail before it initializes its logger (for
                    # example while loading data).  Check infrequently so the
                    # browser receives a conclusive terminal state instead of
                    # an endless keepalive stream.
                    if idle_polls >= 5:
                        idle_polls = 0
                        # StreamingResponse may iterate in a different worker
                        # thread from the request dependency.  Use a short-
                        # lived session for this watchdog rather than sharing
                        # the request's SQLAlchemy Session across threads.
                        from packages.database.session import SessionLocal

                        status_db = SessionLocal()
                        try:
                            current = status_db.get(BacktestRun, run_id)
                        finally:
                            status_db.close()
                        if current and current.status in {"completed", "failed", "cancelled"}:
                            if current.status != "completed":
                                yield _sse_event({"t": "error", "line": "✗ Backtest ended before terminal output was available"})
                            yield _sse_event({"t": "close", "line": "── stream ended ──"})
                            return
                    yield f": keepalive\n\n"
                    continue
                idle_polls = 0
                if msg.get("type") != "message":
                    continue
                payload = _decode_terminal_event(msg.get("data"))
                if payload is None:
                    continue
                sequence = _event_sequence(payload)
                if sequence and sequence <= last_sequence:
                    continue
                if sequence:
                    last_sequence = sequence
                yield _sse_event(payload)
                if payload.get("t") == "close":
                    return
        except GeneratorExit:
            pass
        except Exception:
            yield _sse_event({"t": "error", "line": "Terminal stream interrupted"})
        finally:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
