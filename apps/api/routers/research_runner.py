"""Isolated Python research runner API.

POST /api/research/run queues user code for containerized execution in the
worker; GET /api/research/run/{id} reports status, metrics, figure URLs, and
the bounded log tail. User code never executes in the API process.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from apps.api.services.research_runner_service import (
    MAX_CODE_BYTES,
    cancel_research_run,
    create_research_run,
    figure_path,
    queue_research_run,
    serialize_research_run,
)
from packages.database.models import ResearchRun, User
from packages.research_runner.validator import CodeValidationError

router = APIRouter(prefix="/research", tags=["research-runner"])


class ResearchRunRequest(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_BYTES)
    dataset_refs: list[str] = Field(default_factory=list, max_length=8)
    limits: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)


@router.post("/run")
def create_run(payload: ResearchRunRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = create_research_run(
            db,
            user.id,
            payload.code,
            payload.dataset_refs,
            limits=payload.limits,
            idempotency_key=payload.idempotency_key,
        )
    except CodeValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "RESEARCH_CODE_REJECTED", "violations": exc.violations}) from exc
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail={"code": "RESEARCH_RUN_NOT_ENTITLED", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row.status == "queued":
        try:
            queue_research_run(db, row.id)
            db.refresh(row)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={"code": "RESEARCH_QUEUE_UNAVAILABLE", "message": str(exc)}) from exc
    response = {"run_id": row.id, "status": row.status}
    if row.status == "unavailable":
        response["error"] = row.error
    return response


@router.get("/run/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(ResearchRun, run_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research run not found")
    return serialize_research_run(row)


@router.post("/run/{run_id}/cancel")
def cancel_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = cancel_research_run(db, user.id, run_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return serialize_research_run(row)


@router.get("/run/{run_id}/files/{name}")
def download_figure(run_id: str, name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(ResearchRun, run_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research run not found")
    path = figure_path(row, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Figure not found")
    return FileResponse(path, filename=path.name)
