from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.agent_service import AgentLimitError, AgentModelInvalidError, AgentModelPlanError, AgentModelUnavailableError, agent_model_options, create_conversation, owned_conversation, quota_state, quote_agent_run, recover_stale_runs, serialize_conversation, serialize_message, start_run, stream_run
from apps.api.services.credit_service import InsufficientCreditsError, refund_task
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.skill_service import skill_registry
from packages.billing.metering import CreditReservation
from packages.database.models import AgentConversation, AgentMessage, AgentRun, User, utcnow
from packages.skills.registry import SkillResolutionError, update_skill_runs


router = APIRouter(prefix="/agent", tags=["agent"])


class ConversationRequest(BaseModel):
    title: str | None = None


class ConversationPatch(BaseModel):
    title: str | None = None
    archived: bool | None = None


class MessageRequest(BaseModel):
    content: str
    locale: str = "en"
    data_sources: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)
    custom_prompt: str = ""
    attachments: list[dict] = Field(default_factory=list)
    model: str | None = None


class AgentQuoteRequest(BaseModel):
    content: str = ""
    data_sources: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)
    custom_prompt: str = ""
    attachments: list[dict] = Field(default_factory=list)
    model: str | None = None


@router.get("/quota")
def get_quota(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return quota_state(db, user)


@router.get("/capabilities")
def capabilities(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    entitlement = get_user_entitlement(db, user.id)
    return {"capabilities": entitlement, "quota": quota_state(db, user), "models": agent_model_options(db, user), "skills": skill_registry(db, user).list_visible()}


@router.post("/quote")
def agent_quote(payload: AgentQuoteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return quote_agent_run(db, user, payload.content, context={
            "data_sources": payload.data_sources,
            "skills": payload.skills,
            "skill_refs": payload.skill_refs,
            "custom_prompt": payload.custom_prompt,
            "attachments": payload.attachments,
            "model": payload.model,
        })
    except AgentModelInvalidError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc), "message": "The selected Agent model is invalid."}) from exc
    except AgentModelPlanError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc), "message": "GPT-5.6 Luna requires an eligible plan."}) from exc
    except AgentModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail={"code": str(exc), "message": "GPT-5.6 Luna is currently unavailable."}) from exc
    except SkillResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/conversations")
def conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    recover_stale_runs(db)
    rows = db.query(AgentConversation).filter(AgentConversation.user_id == user.id, AgentConversation.status != "deleted").order_by(AgentConversation.updated_at.desc()).all()
    return {"conversations": [serialize_conversation(row) for row in rows]}


@router.post("/conversations")
def new_conversation(payload: ConversationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"conversation": serialize_conversation(create_conversation(db, user, payload.title))}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = owned_conversation(db, user, conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    messages = db.query(AgentMessage).filter_by(conversation_id=row.id, user_id=user.id).order_by(AgentMessage.created_at).all()
    return {"conversation": serialize_conversation(row), "messages": [serialize_message(db, item) for item in messages]}


@router.patch("/conversations/{conversation_id}")
def update_conversation(conversation_id: str, payload: ConversationPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = owned_conversation(db, user, conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if payload.title is not None:
        row.title = payload.title.strip()[:160] or row.title
    if payload.archived is not None:
        row.archived_at = utcnow() if payload.archived else None
        row.status = "archived" if payload.archived else "active"
    db.commit()
    return {"conversation": serialize_conversation(row)}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = owned_conversation(db, user, conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    row.status = "deleted"
    row.archived_at = utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/conversations")
def delete_all_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    count = db.query(AgentConversation).filter(
        AgentConversation.user_id == user.id,
        AgentConversation.status != "deleted"
    ).update({"status": "deleted", "archived_at": utcnow()}, synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": count}


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    owned_conversation(db, user, conversation_id)
    rows = db.query(AgentMessage).filter_by(conversation_id=conversation_id, user_id=user.id).order_by(AgentMessage.created_at).all()
    return {"messages": [serialize_message(db, row) for row in rows]}


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, payload: MessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> StreamingResponse:
    try:
        row = owned_conversation(db, user, conversation_id)
        run = start_run(db, user, row, payload.content, context={"data_sources": payload.data_sources, "skills": payload.skills, "skill_refs": payload.skill_refs, "custom_prompt": payload.custom_prompt, "attachments": payload.attachments, "model": payload.model})
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentLimitError as exc:
        raise HTTPException(status_code=429, detail={"code": str(exc)}) from exc
    except AgentModelInvalidError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc), "message": "The selected Agent model is invalid."}) from exc
    except AgentModelPlanError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc), "message": "GPT-5.6 Luna requires an eligible plan."}) from exc
    except AgentModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail={"code": str(exc), "message": "GPT-5.6 Luna is currently unavailable."}) from exc
    except SkillResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail={"code": "INSUFFICIENT_CREDITS"}) from exc
    return StreamingResponse(stream_run(db, user, run.id, payload.locale), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/messages/{message_id}/regenerate")
def regenerate(message_id: str, payload: MessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> StreamingResponse:
    assistant = db.query(AgentMessage).filter_by(id=message_id, user_id=user.id, role="assistant").one_or_none()
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant message not found")
    previous = db.query(AgentMessage).filter(AgentMessage.conversation_id == assistant.conversation_id, AgentMessage.user_id == user.id, AgentMessage.role == "user", AgentMessage.created_at <= assistant.created_at).order_by(AgentMessage.created_at.desc()).first()
    if not previous:
        raise HTTPException(status_code=400, detail="Original user message not found")
    conversation = owned_conversation(db, user, assistant.conversation_id)
    supplied = bool(payload.data_sources or payload.skills or payload.skill_refs or payload.custom_prompt or payload.attachments or payload.model)
    context = {"data_sources": payload.data_sources, "skills": payload.skills, "skill_refs": payload.skill_refs, "custom_prompt": payload.custom_prompt, "attachments": payload.attachments, "model": payload.model} if supplied else (previous.context_json or {})
    try:
        run = start_run(db, user, conversation, previous.content, context=context)
    except AgentLimitError as exc:
        raise HTTPException(status_code=429, detail={"code": str(exc)}) from exc
    except AgentModelInvalidError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc), "message": "The selected Agent model is invalid."}) from exc
    except AgentModelPlanError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc), "message": "GPT-5.6 Luna requires an eligible plan."}) from exc
    except AgentModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail={"code": str(exc), "message": "GPT-5.6 Luna is currently unavailable."}) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail={"code": "INSUFFICIENT_CREDITS"}) from exc
    except SkillResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return StreamingResponse(stream_run(db, user, run.id, payload.locale), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.query(AgentRun).filter_by(id=run_id, user_id=user.id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    if row.status in {"pending", "running"}:
        was_pending = row.status == "pending"
        row.status = "canceled"
        if was_pending and row.credit_cost and not row.credit_refunded:
            refund_task(
                db,
                user.id,
                CreditReservation(f"agent-charge:{row.id}", row.credit_cost),
                "user_cancelled_before_start",
                metadata={"run_id": row.id},
            )
            row.credit_refunded = True
        update_skill_runs(db, row.id, status="canceled", credits_used=0, error_code="USER_CANCELED")
        db.commit()
    return {"id": row.id, "status": row.status}
