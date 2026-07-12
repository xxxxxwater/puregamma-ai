from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.backtest_service import run_backtest
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from packages.database.models import BacktestRun, User


router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy_name: str = "BTC momentum breakout"
    asset: str = "BTC"
    params: dict = {}
    engine: str = "mock"
    strategy_id: str | None = None


def serialize_run(row: BacktestRun) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "strategy_name": row.strategy_name,
        "asset": row.asset,
        "params": row.params_json,
        "result": row.result_json,
        "credits_spent": row.credits_spent,
        "created_at": row.created_at.isoformat(),
    }


@router.post("")
def create(payload: BacktestRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return {"backtest": serialize_run(run_backtest(db, user.id, payload.strategy_name, payload.asset, payload.params, engine=payload.engine, strategy_id=payload.strategy_id))}
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}")
def get(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(BacktestRun, run_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return {"backtest": serialize_run(row)}
