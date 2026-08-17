"""Harness deep-research HTTP contract (docs/mobile/MOBILE_API_CONTRACT.md §2).

GET/POST /api/research/runs* — create, list, detail, cancel, retry,
evidence, artifacts and a lightweight SSE progress stream. All rows are
ownership-checked against the authenticated user; no admin surface here.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services import harness_run_service
from apps.api.services.harness_run_service import (
    HarnessDisabledError,
    HarnessQuotaError,
    HarnessStateConflict,
    HARNESS_SKILL_ALLOWLIST,
)
from packages.database.models import HarnessResearchRun, User

router = APIRouter(prefix="/research", tags=["harness-research"])


class HarnessRunCreate(BaseModel):
    name: str = Field(default="", max_length=120)
    prompt: str = Field(min_length=1, max_length=4000)
    data_sources: list[str] = Field(default_factory=list, max_length=4)
    skill: str = Field(default="harness_deep_research", max_length=64)


def _serialize(db: Session, run: HarnessResearchRun) -> dict:
    return harness_run_service.serialize_harness_run(
        run,
        evidence_count=len(harness_run_service.run_evidence(db, run)),
    )


@router.post("/runs", status_code=201)
def create_run(
    payload: HarnessRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row, created = harness_run_service.create_harness_run(
            db,
            user.id,
            name=payload.name,
            prompt=payload.prompt,
            data_sources=payload.data_sources,
            skill=payload.skill,
        )
    except HarnessDisabledError as exc:
        raise HTTPException(status_code=403, detail={"code": "HARNESS_DISABLED", "message": str(exc)}) from exc
    except HarnessQuotaError as exc:
        raise HTTPException(status_code=429, detail={"code": "HARNESS_QUOTA_EXCEEDED", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "HARNESS_BAD_REQUEST", "message": str(exc)}) from exc

    if row.status == "queued":
        try:
            harness_run_service.queue_harness_run(db, row.id)
            db.refresh(row)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={"code": "HARNESS_QUEUE_UNAVAILABLE", "message": str(exc)}) from exc
    return {"run": _serialize(db, row), "created": created}


@router.get("/runs")
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows, total = harness_run_service.list_harness_runs(db, user.id, limit=limit, offset=offset)
    return {"runs": [_serialize(db, row) for row in rows], "total": total, "limit": limit, "offset": offset}


def _own_run(db: Session, user: User, run_id: str) -> HarnessResearchRun:
    row = (
        db.query(HarnessResearchRun)
        .filter(HarnessResearchRun.id == run_id, HarnessResearchRun.user_id == user.id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return row


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"run": _serialize(db, _own_run(db, user, run_id))}


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = harness_run_service.cancel_harness_run(db, user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HarnessStateConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "message": str(exc)}) from exc
    return {"run": _serialize(db, row)}


@router.post("/runs/{run_id}/retry")
def retry_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = harness_run_service.retry_harness_run(db, user.id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HarnessStateConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "message": str(exc)}) from exc
    except HarnessQuotaError as exc:
        raise HTTPException(status_code=429, detail={"code": "HARNESS_QUOTA_EXCEEDED", "message": str(exc)}) from exc
    return {"run": _serialize(db, row)}


@router.get("/runs/{run_id}/evidence")
def get_evidence(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    run = _own_run(db, user, run_id)
    evidence = harness_run_service.run_evidence(db, run)
    return {"evidence": evidence, "total": len(evidence)}


@router.get("/runs/{run_id}/artifacts")
def get_artifacts(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    run = _own_run(db, user, run_id)
    return {"artifacts": harness_run_service.run_artifacts(db, run)}


@router.get("/runs/{run_id}/events")
def stream_events(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Lightweight SSE: poll the run status every 2s until terminal (max 90s).

    Clients must ignore unknown events and fall back to GET /runs/{id} on
    reconnect — this stream never blocks forever and never holds a DB
    transaction open between polls.
    """
    row = _own_run(db, user, run_id)
    last_status = row.status

    def event_stream():
        nonlocal last_status
        yield _sse("run.state", {"run_id": run_id, "status": last_status, "updated_at": str(row.updated_at)})
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            time.sleep(2)
            fresh = db.get(HarnessResearchRun, run_id)
            if fresh is None or fresh.user_id != user.id:
                yield _sse("run.failed", {"run_id": run_id, "message": "run disappeared"})
                return
            if fresh.status != last_status:
                last_status = fresh.status
                yield _sse("run.state", {"run_id": run_id, "status": fresh.status, "updated_at": str(fresh.updated_at)})
            if fresh.status == "completed":
                yield _sse("run.completed", {"run_id": run_id, "verified": True, "degraded": False})
                return
            if fresh.status == "degraded":
                yield _sse("run.completed", {"run_id": run_id, "verified": False, "degraded": True})
                return
            if fresh.status == "failed":
                yield _sse("run.failed", {"run_id": run_id, "message": fresh.error_summary or "failed"})
                return
            if fresh.status == "canceled":
                yield _sse("run.canceled", {"run_id": run_id})
                return
            if fresh.status == "timed_out":
                yield _sse("run.failed", {"run_id": run_id, "message": "timed out"})
                return
        yield _sse("run.state", {"run_id": run_id, "status": last_status, "updated_at": str(fresh.updated_at) if fresh else None})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(event: str, data: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
