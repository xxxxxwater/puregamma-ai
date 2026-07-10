from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services import billing_service
from packages.database.models import User


router = APIRouter(prefix="/billing", tags=["billing"])


class PlanRequest(BaseModel):
    plan_name: str


@router.get("/subscription")
def subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return billing_service.get_subscription(db, user.id)


@router.get("/credits")
def credits(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return billing_service.get_credits(db, user.id)


@router.post("/create-checkout-session")
def checkout(payload: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        result = billing_service.create_checkout_session(db, user.id, payload.plan_name)
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create-payment-link-checkout")
def payment_link_checkout(payload: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        result = billing_service.create_payment_link_checkout(db, user.id, payload.plan_name)
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create-portal-session")
def portal(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.create_portal_session(db, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel-subscription")
def cancel_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.set_subscription_cancel_at_period_end(db, user.id, True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reactivate-subscription")
def reactivate_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.set_subscription_cancel_at_period_end(db, user.id, False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mock-upgrade")
def mock_upgrade(payload: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.mock_upgrade(db, user.id, payload.plan_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
