"""Authenticated read-only projection for a JEV advisory observation."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_current_user
from apps.api.services.jev_advisory_service import get_reader
from packages.database.models import User

router = APIRouter(prefix="/jev-trader", tags=["jev-advisory"])


@router.get("/status")
def status(_user: User = Depends(get_current_user)) -> dict:
    """Return validated, non-executable advisory telemetry or an honest state."""
    return get_reader().status()
