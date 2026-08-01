from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.backtest_service import run_backtest
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from apps.api.services.unified_backtest_service import (
    cancel_unified_run,
    export_run,
    save_run_as_strategy,
    serialize_artifact,
    serialize_saved_strategy,
)
from apps.api.services.unified_backtest_service import create_unified_run, serialize_unified_run
from apps.api.services.skill_service import begin_module_skill_invocation, finish_module_skill_invocation
from packages.billing.credits import cost_for
from packages.backtest.artifacts import artifact_root
from packages.database.models import BacktestArtifact, BacktestRun, User
from packages.skills.registry import SkillResolutionError
from apps.api.routers.backtest_lab import BacktestDispatchUnavailable


router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy_name: str = "BTC momentum breakout"
    asset: str = "BTC"
    params: dict = {}
    engine: str = "vectorbt"
    strategy_id: str | None = None
    idempotency_key: str | None = None
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)


def serialize_run(row: BacktestRun, artifacts: list[BacktestArtifact] | None = None) -> dict:
    result = row.result_json or {}
    return {
        "id": row.id,
        "user_id": row.user_id,
        "strategy_name": row.strategy_name,
        "asset": row.asset,
        "params": row.params_json,
        "result": row.result_json,
        "status": row.status,
        "engine": row.engine,
        "spec": row.spec_json or {},
        "data_snapshot": row.data_snapshot_json or {},
        "assumptions": row.assumptions_json or {},
        "error": row.error_json or {},
        "strategy_id": row.strategy_id,
        "charts": result.get("charts", {}),
        "trades": result.get("trades", []),
        "positions": result.get("positions", []),
        "artifacts": [serialize_artifact(item) for item in artifacts] if artifacts is not None else [],
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
        if payload.engine.lower().strip() == "vectorbt":
            params = payload.params or {}
            spec = {"name": payload.strategy_name, "mode": "daily", "signal": params.get("signal", "momentum"), "assets": [payload.asset.upper()], "fast_window": int(params.get("fast_window", 12)), "slow_window": int(params.get("slow_window", 26)), "entry_threshold": float(params.get("entry_threshold", 0)), "exit_threshold": float(params.get("exit_threshold", 0)), "long_short": bool(params.get("long_short", False)), "max_position": float(params.get("max_position", 1.0)), "fee_bps": float(params.get("fee_bps", 10)), "slippage_bps": float(params.get("slippage_bps", 0)), "thesis": params.get("thesis", "")}
            row = create_unified_run(db, user.id, spec, window_days=int(params.get("lookback_days", 30)), idempotency_key=payload.idempotency_key, context_meta={"skill_invocation_id": invocation_id})
            from apps.api.routers.backtest_lab import _dispatch_or_run
            _dispatch_or_run(db, row.id)
            db.refresh(row)
        else:
            row = run_backtest(db, user.id, payload.strategy_name, payload.asset, payload.params, engine=payload.engine, strategy_id=payload.strategy_id, idempotency_key=payload.idempotency_key)
        if row.status == "completed":
            finish_module_skill_invocation(db, invocation_id, status="completed", credits_used=row.credits_spent, output_summary=f"{row.strategy_name} / {row.asset}", evidence={"backtest_id": row.id, "source": row.result_json.get("source") or row.engine, "is_mock": row.result_json.get("is_mock", False)})
        db.commit()
        return {"backtest": serialize_unified_run(row) if row.engine == "vectorbt" else serialize_run(row)}
    except SkillResolutionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        db.rollback()
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="failed", credits_used=0, error_code="BACKTEST_REJECTED")
            db.commit()
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except BacktestDispatchUnavailable as exc:
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="failed", credits_used=0, error_code="BACKTEST_QUEUE_UNAVAILABLE")
            db.commit()
        raise HTTPException(status_code=503, detail={"code": "BACKTEST_QUEUE_UNAVAILABLE", "message": str(exc)}) from exc
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
    artifacts = db.query(BacktestArtifact).filter_by(backtest_id=row.id, user_id=user.id).order_by(BacktestArtifact.created_at.asc()).all()
    return {"backtest": serialize_run(row, artifacts=artifacts)}


@router.post("/{run_id}/cancel")
def cancel(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = cancel_unified_run(db, user.id, run_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {"backtest": serialize_unified_run(row)}


@router.post("/{run_id}/save-as-strategy")
def save_as_strategy(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        payload = save_run_as_strategy(db, user.id, run_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {"strategy": serialize_saved_strategy(payload)}


@router.post("/{run_id}/export")
def export_backtest(run_id: str, format: str = "json", db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return {"artifact": serialize_artifact(export_run(db, user.id, run_id, format))}
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
