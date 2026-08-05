"""Hidden compatibility contracts for capabilities under active development.

These endpoints are deliberately not public product routes. Every request needs
an authenticated admin and the internal runtime secret. A feature flag only
exposes the contract; it does not bypass risk, entitlement or trading gates.
"""
from __future__ import annotations

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, require_admin
from apps.api.dependencies import get_db
from apps.api.services.portfolio_service import portfolio_context, portfolio_view
from packages.risk.engine import evaluate_portfolio
from packages.database.models import User

router = APIRouter(prefix="/internal", tags=["internal-compatibility"], include_in_schema=False)


def internal_admin(
    user: User = Depends(get_current_user),
    x_internal_runtime_secret: str | None = Header(default=None),
) -> User:
    require_admin(user)
    expected = get_settings().internal_runtime_secret
    if not expected or not x_internal_runtime_secret or not hmac.compare_digest(x_internal_runtime_secret, expected):
        raise HTTPException(status_code=403, detail="Internal capability access denied")
    return user


def _capability(name: str, *, enabled: bool, implemented: bool = False, production_allowed: bool = False, partial: bool = False) -> dict:
    status = "PARTIAL" if enabled and implemented and partial else "HEALTHY" if enabled and implemented else "PLACEHOLDER" if enabled else "DISABLED"
    if enabled and not implemented:
        status = "NOT_IMPLEMENTED"
    return {
        "capability_name": name,
        "mode": "hidden_compatibility",
        "configured": enabled,
        "enabled": enabled,
        "healthy": bool(enabled and implemented and not partial),
        "production_allowed": production_allowed and implemented,
        "mock": False,
        "fallback": False,
        "status": status,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "last_success_at": None,
        "error_code": "CAPABILITY_PARTIAL" if partial else None if implemented else "CAPABILITY_NOT_IMPLEMENTED",
        "error_message": "Portfolio snapshot compatibility is available; Decimal fact-layer/reconciliation is still pending." if partial else None if implemented else "Hidden contract only; implementation is not enabled.",
    }


@router.get("/capabilities")
def capabilities(_: User = Depends(internal_admin)) -> dict:
    settings = get_settings()
    return {
        "environment": settings.app_environment,
        "public_exposure": False,
        "capabilities": [
            _capability("portfolio_ai", enabled=settings.hidden_portfolio_ai_enabled, implemented=True, partial=True),
            _capability("risk_copilot", enabled=settings.hidden_risk_copilot_enabled),
            _capability("realtime_analytics", enabled=settings.hidden_realtime_analytics_enabled),
            _capability("trading_mcp", enabled=settings.hidden_trading_mcp_enabled),
        ],
    }


def _guard(flag: bool, name: str) -> None:
    if not flag:
        raise HTTPException(status_code=404, detail={"code": "CAPABILITY_DISABLED", "capability": name})
    raise HTTPException(status_code=501, detail={"code": "CAPABILITY_NOT_IMPLEMENTED", "capability": name})


class RiskPreviewRequest(BaseModel):
    portfolio_snapshot_id: str = Field(default="current", min_length=1, max_length=200)
    scenario: str = Field(default="baseline", max_length=80)


@router.get("/portfolio-ai/status")
def portfolio_status(_: User = Depends(internal_admin)) -> dict:
    settings = get_settings()
    return _capability("portfolio_ai", enabled=settings.hidden_portfolio_ai_enabled, implemented=True, partial=True)


@router.get("/portfolio-ai/snapshot")
def portfolio_snapshot(db: Session = Depends(get_db), user: User = Depends(internal_admin)) -> dict:
    if not get_settings().hidden_portfolio_ai_enabled:
        _guard(False, "portfolio_ai")
    snapshot = portfolio_view(db, user)
    snapshot["capability"] = "portfolio_ai"
    snapshot["data_quality"] = "STALE" if snapshot.get("stale") else "FRESH" if snapshot.get("connected") else "NOT_CONNECTED"
    snapshot["mock"] = False
    return snapshot


@router.get("/realtime/status")
def realtime_status(_: User = Depends(internal_admin)) -> dict:
    _guard(get_settings().hidden_realtime_analytics_enabled, "realtime_analytics")
    return {}


@router.get("/trading-mcp/status")
def trading_mcp_status(_: User = Depends(internal_admin)) -> dict:
    _guard(get_settings().hidden_trading_mcp_enabled, "trading_mcp")
    return {}


@router.post("/risk-copilot/evaluate")
def risk_evaluate(payload: RiskPreviewRequest, db: Session = Depends(get_db), user: User = Depends(internal_admin)) -> dict:
    if not get_settings().hidden_risk_copilot_enabled:
        _guard(False, "risk_copilot")
    context = portfolio_context(db, user.id, detailed=True)
    assessment = evaluate_portfolio(context, payload.scenario)
    if payload.portfolio_snapshot_id != "current" and payload.portfolio_snapshot_id != assessment.snapshot_id:
        raise HTTPException(status_code=409, detail={"code": "SNAPSHOT_MISMATCH", "snapshot_id": assessment.snapshot_id})
    return assessment.to_dict()
