from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.credit_service import InsufficientCreditsError, quote_task, refund_task, reserve_task, settle_task
from apps.api.services.signal_service import scan_signals, serialize_signal
from packages.database.models import Signal, User


router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/scan")
def scan(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    quote = quote_task(task_type="sentiment_scan", async_execution=True)
    reservation = None
    try:
        reservation = reserve_task(
            db,
            user.id,
            quote,
            f"signal-scan:{user.id}:{uuid.uuid4()}",
        )
        db.commit()
        rows = scan_signals(db)
        settle_task(db, user.id, reservation, quote.credits, metadata={"signals": len(rows)})
        db.commit()
        return {"signals": [serialize_signal(row) for row in rows]}
    except InsufficientCreditsError as exc:
        db.rollback()
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        if reservation:
            refund_task(db, user.id, reservation, "SIGNAL_SCAN_FAILED")
            db.commit()
        raise


@router.get("")
def list_signals(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(Signal).order_by(Signal.created_at.desc()).limit(100).all()
    return {"signals": [serialize_signal(row) for row in rows]}
