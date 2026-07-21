from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.backtest_lab_service import (
    LabRateLimited,
    generate_lab_spec,
    lab_status,
    list_lab_runs,
    run_lab,
    serialize_lab_run,
)
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from packages.backtest.daily_data import LAB_SYMBOLS, refresh_daily_candles
from packages.database.models import BacktestLabRun, User

router = APIRouter(prefix="/backtest-lab", tags=["backtest-lab"])


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
        row = run_lab(db, user.id, payload.spec, window_days=payload.window_days, idempotency_key=payload.idempotency_key, context_meta=payload.context_meta)
    except LabRateLimited as exc:
        raise HTTPException(status_code=429, detail={"code": "BACKTEST_LAB_DAILY_LIMIT", "message": str(exc)}) from exc
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run": serialize_lab_run(row)}


@router.get("/runs")
def runs(limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"runs": [serialize_lab_run(row) for row in list_lab_runs(db, user.id, limit=limit)]}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(BacktestLabRun, run_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return {"run": serialize_lab_run(row)}


@router.post("/data/refresh")
def refresh_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    stats = refresh_daily_candles(db, list(LAB_SYMBOLS))
    return {"stats": stats, **lab_status(db)}
