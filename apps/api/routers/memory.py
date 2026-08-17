"""Memory service HTTP contract (docs/mobile/MOBILE_API_CONTRACT.md §3).

User-owned, scope-isolated memory management: settings, items, proposals
(approve/reject), delete, clear and export. All operations are ownership
checked; the trading namespace is read-only by policy and never exposed
through these write endpoints.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from packages.database.models import MemoryProposal, MemoryScopeSetting, User, UserMemory, utcnow
from packages.memory.policy import MEMORY_NAMESPACES, WRITE_DISABLED_NAMESPACES, redact_secrets
from packages.memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])

# Contract scope -> namespace mapping. short_term covers conversational
# memory, mid_term covers research/portfolio memory.
SCOPE_NAMESPACES: dict[str, tuple[str, ...]] = {
    "short_term": ("chat", "secretary"),
    "mid_term": ("research", "portfolio"),
    "all": tuple(sorted(MEMORY_NAMESPACES - WRITE_DISABLED_NAMESPACES)),
}

SETTING_TO_SCOPES: dict[str, tuple[str, ...]] = {
    "short_term_enabled": ("chat", "secretary"),
    "mid_term_enabled": ("research", "portfolio"),
    "conversation_summary_enabled": ("chat",),
    "research_memory_enabled": ("research",),
    "portfolio_memory_enabled": ("portfolio",),
}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _preview(content_json: dict | None, limit: int = 200) -> str:
    raw = json.dumps(content_json or {}, ensure_ascii=False)
    cleaned = redact_secrets(raw)
    return cleaned[:limit]


def _scope_enabled(db: Session, user_id: str, scope: str) -> bool:
    row = (
        db.query(MemoryScopeSetting)
        .filter(MemoryScopeSetting.user_id == user_id, MemoryScopeSetting.scope == scope)
        .one_or_none()
    )
    return row.enabled if row is not None else True


def _service() -> MemoryService:
    settings = get_settings()
    return MemoryService(
        auto_accept_low_risk=settings.memory_auto_accept_low_risk,
        summary_ttl_days=settings.memory_summary_ttl_days,
    )


def _item_json(memory: UserMemory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "scope": memory.namespace,
        "kind": memory.kind,
        "content_preview": _preview(memory.content_json),
        "status": memory.status,
        "created_at": _iso(memory.created_at),
        "expires_at": _iso(memory.expires_at),
    }


def _proposal_json(proposal: MemoryProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "scope": proposal.namespace,
        "kind": proposal.kind,
        "content_preview": _preview(proposal.content_json),
        "source": proposal.proposed_by or "model",
        "status": proposal.status,
        "created_at": _iso(proposal.created_at),
        "expires_at": _iso(proposal.expires_at),
    }


@router.get("/settings")
def get_settings_view(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    settings = get_settings()
    chat = _scope_enabled(db, user.id, "chat")
    secretary = _scope_enabled(db, user.id, "secretary")
    research = _scope_enabled(db, user.id, "research")
    portfolio = _scope_enabled(db, user.id, "portfolio")
    return {
        "settings": {
            "short_term_enabled": chat and secretary,
            "mid_term_enabled": research or portfolio,
            "conversation_summary_enabled": chat,
            "research_memory_enabled": research,
            "portfolio_memory_enabled": portfolio,
            "consent_required": False,
            "retention_days": settings.memory_summary_ttl_days,
        }
    }


class MemorySettingsPatch(BaseModel):
    short_term_enabled: bool | None = None
    mid_term_enabled: bool | None = None
    conversation_summary_enabled: bool | None = None
    research_memory_enabled: bool | None = None
    portfolio_memory_enabled: bool | None = None
    consent_granted: bool = False


@router.patch("/settings")
def patch_settings(
    payload: MemorySettingsPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not get_settings().memory_service_enabled:
        raise HTTPException(status_code=403, detail={"code": "MEMORY_DISABLED", "message": "Memory service is disabled"})
    service = _service()
    requested = payload.model_dump(exclude_none=True)
    requested.pop("consent_granted", None)
    for key, enabled in requested.items():
        if not isinstance(enabled, bool):
            continue
        for scope in SETTING_TO_SCOPES.get(key, ()):
            if scope in WRITE_DISABLED_NAMESPACES:
                continue
            service.set_scope_enabled(db, user_id=user.id, scope=scope, enabled=enabled)
    return get_settings_view(db, user)


@router.get("/items")
def list_items(
    scope: str = "short_term",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    namespaces = SCOPE_NAMESPACES.get(scope)
    if namespaces is None:
        raise HTTPException(status_code=400, detail={"code": "MEMORY_BAD_SCOPE", "message": "scope must be short_term or mid_term"})
    rows = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user.id, UserMemory.namespace.in_(namespaces), UserMemory.status == "active")
        .order_by(UserMemory.updated_at.desc())
        .all()
    )
    return {"items": [_item_json(row) for row in rows], "total": len(rows)}


@router.get("/proposals")
def list_proposals(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = _service().list_proposals(db, user_id=user.id, status=status)
    return {"proposals": [_proposal_json(row) for row in rows]}


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        _service().approve_proposal(db, user_id=user.id, proposal_id=proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    proposal = (
        db.query(MemoryProposal)
        .filter(MemoryProposal.id == proposal_id, MemoryProposal.user_id == user.id)
        .one_or_none()
    )
    return {"proposal": _proposal_json(proposal) if proposal is not None else {"id": proposal_id, "status": "user_approved"}}


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        _service().reject_proposal(db, user_id=user.id, proposal_id=proposal_id, reason="rejected by user")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    proposal = (
        db.query(MemoryProposal)
        .filter(MemoryProposal.id == proposal_id, MemoryProposal.user_id == user.id)
        .one_or_none()
    )
    return {"proposal": _proposal_json(proposal) if proposal is not None else {"id": proposal_id, "status": "rejected"}}


@router.delete("/items/{memory_id}")
def delete_item(
    memory_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _service().delete_memory(db, user_id=user.id, memory_id=memory_id)
    return {"deleted": True}


class MemoryClearRequest(BaseModel):
    scope: str = Field(default="all")


@router.post("/clear")
def clear_memories(
    payload: MemoryClearRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    namespaces = SCOPE_NAMESPACES.get(payload.scope)
    if namespaces is None:
        raise HTTPException(status_code=400, detail={"code": "MEMORY_BAD_SCOPE", "message": "scope must be all, short_term or mid_term"})
    service = _service()
    cleared = 0
    for namespace in namespaces:
        cleared += service.clear_namespace(db, user_id=user.id, namespace=namespace)
    return {"cleared": cleared}


@router.get("/export", response_model=None)
def export_memories(
    download: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = _service().export_memories(db, user_id=user.id)
    if download:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="puregamma-memory-{user.id[:8]}.json"'},
        )
    expires_at = utcnow() + timedelta(hours=1)
    return {"url": "/api/memory/export?download=1", "expires_at": _iso(expires_at)}
