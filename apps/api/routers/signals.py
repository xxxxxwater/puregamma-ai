from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.credit_service import InsufficientCreditsError, consume_credits
from apps.api.services.signal_service import scan_signals, serialize_signal
from packages.billing.credits import cost_for
from packages.database.models import Signal, User


router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/scan")
def scan(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        consume_credits(db, user.id, "sentiment_scan", cost_for("sentiment_scan"))
        rows = scan_signals(db)
        return {"signals": [serialize_signal(row) for row in rows]}
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.get("")
def list_signals(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(Signal).order_by(Signal.created_at.desc()).limit(100).all()
    return {"signals": [serialize_signal(row) for row in rows]}
