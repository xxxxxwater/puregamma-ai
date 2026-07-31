from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from packages.database.models import Asset


router = APIRouter(tags=["assets"])


@router.get("/assets")
def assets(db: Session = Depends(get_db)) -> dict:
    rows = db.query(Asset).order_by(Asset.symbol).all()
    return {"assets": [{"symbol": item.symbol, "name": item.name, "category": item.category, "is_active": item.is_active} for item in rows]}
