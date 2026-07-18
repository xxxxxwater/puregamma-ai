from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.backtest_service import run_backtest
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from apps.api.services.skill_service import begin_module_skill_invocation, finish_module_skill_invocation
from packages.billing.credits import cost_for
from packages.database.models import BacktestRun, User
from packages.skills.registry import SkillResolutionError


router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy_name: str = "BTC momentum breakout"
    asset: str = "BTC"
    params: dict = {}
    engine: str = "nautilus"
    strategy_id: str | None = None
    idempotency_key: str | None = None
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)


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
    invocation_id = None
    try:
        invocation_id, _ = begin_module_skill_invocation(
            db,
            user,
            payload.skill_refs,
            trigger_source="nautilus",
            input_payload={"query": f"Backtest {payload.strategy_name} on {payload.asset}", "strategy_name": payload.strategy_name, "asset": payload.asset, "params": payload.params, "engine": payload.engine},
            estimated_credits=cost_for("backtest"),
            required_tool="run_nautilus_backtest",
            invocation_id=f"backtest-skill:{user.id}:{payload.idempotency_key}" if payload.idempotency_key else None,
        )
        db.commit()
        row = run_backtest(db, user.id, payload.strategy_name, payload.asset, payload.params, engine=payload.engine, strategy_id=payload.strategy_id, idempotency_key=payload.idempotency_key)
        finish_module_skill_invocation(db, invocation_id, status="completed", credits_used=row.credits_spent, output_summary=f"{row.strategy_name} / {row.asset}", evidence={"backtest_id": row.id, "source": row.result_json.get("source"), "is_mock": row.result_json.get("is_mock")})
        db.commit()
        return {"backtest": serialize_run(row)}
    except SkillResolutionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        db.rollback()
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="failed", credits_used=0, error_code="BACKTEST_REJECTED")
            db.commit()
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="failed", credits_used=0, error_code="BACKTEST_INVALID")
            db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}")
def get(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(BacktestRun, run_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return {"backtest": serialize_run(row)}
