from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.routers.backtest import serialize_run as serialize_backtest
from apps.api.services.strategy_control_service import (
    StrategyControlError,
    activate_strategy,
    create_strategy,
    modify_strategy,
    preview_activation,
    run_strategy_backtest,
    serialize_activation,
    serialize_intent,
    serialize_run,
    serialize_strategy,
    transition_strategy,
    validate_draft,
)
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.skill_service import begin_module_skill_invocation, finish_module_skill_invocation
from packages.billing.credits import cost_for
from packages.database.models import SignalEvent, StrategyRun, TradingStrategy, User
from packages.trading.policies.safety import LiveExecutionDenied
from packages.trading.runtime_client import RuntimeUnavailable
from packages.skills.registry import SkillResolutionError


router = APIRouter(prefix="/strategies", tags=["strategies"])


class StrategyCreateRequest(BaseModel):
    draft: dict
    conversation_id: str | None = None


class StrategyPatchRequest(BaseModel):
    changes: dict


class BacktestRequest(BaseModel):
    engine: str = "mock"
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)


class ActivationPreviewRequest(BaseModel):
    mode: str = "PAPER"
    account_id: str | None = None
    conversation_id: str | None = None
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)


class ActivationRequest(BaseModel):
    intent_id: str
    confirmation: str = Field(min_length=16, max_length=500)


def error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, SkillResolutionError):
        return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RuntimeUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, InsufficientCreditsError):
        return HTTPException(status_code=402, detail=str(exc))
    if isinstance(exc, (StrategyControlError, LiveExecutionDenied, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Strategy control failed")


@router.post("")
def create(
    payload: StrategyCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {
            "strategy": serialize_strategy(
                db,
                create_strategy(
                    db,
                    user.id,
                    payload.draft,
                    conversation_id=payload.conversation_id,
                    idempotency_key=idempotency_key,
                ),
            )
        }
    except Exception as exc:
        raise error_response(exc) from exc


@router.get("")
def strategies(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    rows = (
        db.query(TradingStrategy)
        .filter_by(user_id=user.id)
        .order_by(TradingStrategy.updated_at.desc())
        .all()
    )
    return {"strategies": [serialize_strategy(db, row) for row in rows]}


@router.get("/{strategy_id}")
def strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = (
        db.query(TradingStrategy)
        .filter_by(id=strategy_id, user_id=user.id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"strategy": serialize_strategy(db, row)}


@router.patch("/{strategy_id}")
def patch(
    strategy_id: str,
    payload: StrategyPatchRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {
            "strategy": serialize_strategy(
                db,
                modify_strategy(
                    db,
                    user.id,
                    strategy_id,
                    payload.changes,
                    idempotency_key=idempotency_key,
                ),
            )
        }
    except Exception as exc:
        raise error_response(exc) from exc


@router.post("/{strategy_id}/validate")
def validate(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = (
        db.query(TradingStrategy)
        .filter_by(id=strategy_id, user_id=user.id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return validate_draft(serialize_strategy(db, row)["draft"])


@router.post("/{strategy_id}/backtest")
def backtest(
    strategy_id: str,
    payload: BacktestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    skill_invocation_id = None
    try:
        skill_invocation_id, _ = begin_module_skill_invocation(
            db,
            user,
            payload.skill_refs,
            trigger_source="nautilus",
            input_payload={"query": f"Backtest strategy {strategy_id}", "strategy_id": strategy_id, "engine": payload.engine},
            estimated_credits=cost_for("backtest"),
            required_tool="run_nautilus_backtest",
        )
        db.commit()
        row = run_strategy_backtest(db, user.id, strategy_id, payload.engine)
        finish_module_skill_invocation(db, skill_invocation_id, status="completed", credits_used=row.credits_spent, output_summary=f"Strategy backtest {strategy_id}", evidence={"backtest_id": row.id, "source": row.result_json.get("source")})
        db.commit()
        return {"backtest": serialize_backtest(row)}
    except Exception as exc:
        db.rollback()
        if skill_invocation_id:
            finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="STRATEGY_BACKTEST_FAILED")
            db.commit()
        raise error_response(exc) from exc


def _preview(
    strategy_id: str,
    mode: str,
    payload: ActivationPreviewRequest,
    idempotency_key: str | None,
    db: Session,
    user: User,
) -> dict:
    skill_invocation_id = None
    try:
        skill_invocation_id, _ = begin_module_skill_invocation(
            db,
            user,
            payload.skill_refs,
            trigger_source="nautilus",
            input_payload={"query": f"Preview {mode} activation for strategy {strategy_id}", "strategy_id": strategy_id, "mode": mode, "account_id": payload.account_id},
            estimated_credits=0,
            allow_order_intent=bool(payload.skill_refs),
            required_tool="generate_order_preview" if payload.skill_refs else None,
        )
        db.commit()
        intent, confirmation = preview_activation(
            db,
            user.id,
            strategy_id,
            mode=mode,
            account_id=payload.account_id,
            conversation_id=payload.conversation_id,
            idempotency_key=idempotency_key,
        )
        finish_module_skill_invocation(db, skill_invocation_id, status="completed", credits_used=0, output_summary=f"{mode} activation preview", evidence={"intent_id": intent.id, "confirmation_required": True})
        db.commit()
        return {"intent": serialize_intent(intent, confirmation)}
    except Exception as exc:
        db.rollback()
        if skill_invocation_id:
            finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="STRATEGY_PREVIEW_FAILED")
            db.commit()
        raise error_response(exc) from exc


@router.post("/{strategy_id}/paper")
def paper(
    strategy_id: str,
    payload: ActivationPreviewRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _preview(strategy_id, "PAPER", payload, idempotency_key, db, user)


@router.post("/{strategy_id}/shadow")
def shadow(
    strategy_id: str,
    payload: ActivationPreviewRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _preview(strategy_id, "SHADOW", payload, idempotency_key, db, user)


@router.post("/{strategy_id}/preview-activation")
def preview(
    strategy_id: str,
    payload: ActivationPreviewRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _preview(strategy_id, payload.mode, payload, idempotency_key, db, user)


@router.post("/{strategy_id}/activate")
def activate(
    strategy_id: str,
    payload: ActivationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        activation, run = activate_strategy(
            db, user.id, strategy_id, payload.intent_id, payload.confirmation
        )
        return {
            "activation": serialize_activation(activation),
            "run": serialize_run(run),
        }
    except Exception as exc:
        raise error_response(exc) from exc


def _transition(strategy_id: str, action: str, db: Session, user: User) -> dict:
    try:
        return {
            "run": serialize_run(transition_strategy(db, user.id, strategy_id, action))
        }
    except Exception as exc:
        raise error_response(exc) from exc


@router.post("/{strategy_id}/pause")
def pause(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _transition(strategy_id, "pause", db, user)


@router.post("/{strategy_id}/resume")
def resume(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _transition(strategy_id, "resume", db, user)


@router.post("/{strategy_id}/stop")
def stop(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _transition(strategy_id, "stop", db, user)


@router.get("/{strategy_id}/performance")
def performance(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = (
        db.query(TradingStrategy)
        .filter_by(id=strategy_id, user_id=user.id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    runs = (
        db.query(StrategyRun)
        .filter_by(strategy_id=row.id, user_id=user.id)
        .order_by(StrategyRun.created_at.desc())
        .all()
    )
    return {"strategy_id": row.id, "runs": [serialize_run(run) for run in runs]}


@router.get("/{strategy_id}/events")
def events(
    strategy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if (
        not db.query(TradingStrategy)
        .filter_by(id=strategy_id, user_id=user.id)
        .one_or_none()
    ):
        raise HTTPException(status_code=404, detail="Strategy not found")
    rows = (
        db.query(SignalEvent)
        .filter_by(strategy_id=strategy_id, user_id=user.id)
        .order_by(SignalEvent.created_at.desc())
        .limit(200)
        .all()
    )
    return {
        "events": [
            {
                "id": row.id,
                "asset": row.asset,
                "direction": row.signal_direction,
                "strength": row.signal_strength,
                "confidence": row.confidence,
                "risk_state": row.risk_state,
                "source_ids": row.source_ids,
                "source_urls": row.source_urls,
                "data_timestamp": row.data_timestamp.isoformat(),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
