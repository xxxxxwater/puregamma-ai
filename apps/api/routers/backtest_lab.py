from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
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

router = APIRouter(prefix="/backtest-lab", tags=["backtest-lab"])


class BacktestDispatchUnavailable(RuntimeError):
    pass


class GenerateSpecRequest(BaseModel):
    idea: str = Field(default="", max_length=2000)
    use_memory: bool = True
    locale: str = "en"


class RunLabRequest(BaseModel):
    spec: dict
    window_days: int = Field(default=365 * 3, ge=30, le=365 * 3)
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
def runs(limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    requested_limit = min(limit, 50)
    unified = [serialize_unified_run(row) for row in db.query(BacktestRun).filter_by(user_id=user.id).order_by(BacktestRun.created_at.desc()).limit(requested_limit).all()]
    legacy = []
    for row in db.query(BacktestLabRun).filter_by(user_id=user.id).order_by(BacktestLabRun.created_at.desc()).limit(requested_limit).all():
        payload = serialize_lab_run(row)
        payload.update({"engine": "legacy_backtest_lab", "run_spec": {"legacy": True}, "drawdown_curve": [], "benchmark_curve": [], "trades": [], "positions": [], "charts": {}, "error": {"message": row.error} if row.error else {}, "credits_reserved": 0, "completed_at": row.updated_at.isoformat() if row.updated_at else None, "is_legacy": True})
        legacy.append(payload)
    merged = sorted([*unified, *legacy], key=lambda item: item.get("created_at") or "", reverse=True)[:requested_limit]
    return {"runs": merged}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(BacktestRun, run_id)
    if row and row.user_id == user.id:
        return {"run": serialize_unified_run(row)}
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
