from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from datetime import timedelta
from urllib.parse import quote
from typing import Literal
from apps.api.services.chat_workspace import MAX_FILE_BYTES, MAX_FILES, MAX_USER_BYTES, save_attachment, owned_attachment, permission_mode, attachment_metadata, remove_attachment, release_conversation_attachments
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.services.agent_service import AgentLimitError, AgentModelInvalidError, AgentModelPlanError, AgentModelUnavailableError, agent_model_options, create_conversation, owned_conversation, quota_state, quote_agent_run, recover_stale_runs, serialize_conversation, serialize_message, start_run, stream_run
from apps.api.services.credit_service import InsufficientCreditsError, refund_task
from apps.api.services.agent_skills import agent_skill_catalog
from apps.api.services.entitlement_service import get_user_entitlement
from packages.billing.metering import CreditReservation
from packages.database.models import AgentConversation, AgentMessage, AgentRun, AgentToolCall, User, utcnow
from packages.skills.registry import SkillResolutionError, update_skill_runs


router = APIRouter(prefix="/agent", tags=["agent"])


class ConversationRequest(BaseModel):
    title: str | None = None


class ConversationPatch(BaseModel):
    permission_mode: Literal["read-only", "workspace-write", "full-access"] | None = None
    acknowledge_full_access: bool = False
    title: str | None = None
    archived: bool | None = None


class MessageRequest(BaseModel):
    content: str
    locale: str = "en"
    research_mode: bool = True
    data_sources: list[str] = Field(default_factory=list)
    # Accepted and IGNORED for backward compatibility: skills are no longer
    # selected by the client.  They follow the DeepSeek Harness default design
    # and are discovered from SKILL.md bundles, so a page cached from before the
    # cutover keeps working while these fields change nothing.  Rejecting them
    # instead would break that page for no security benefit - `_sanitize_context`
    # never reads them.
    skills: list[str] = Field(default_factory=list)
    skill_refs: list[dict] = Field(default_factory=list)
    custom_prompt: str = ""
    attachments: list[dict] = Field(default_factory=list)
    model: str | None = None
    permission_mode: Literal["read-only", "workspace-write", "full-access"] | None = None


class AgentQuoteRequest(BaseModel):
    content: str = ""
    research_mode: bool = True
    data_sources: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)
    custom_prompt: str = ""
    attachments: list[dict] = Field(default_factory=list)
    model: str | None = None
    permission_mode: Literal["read-only", "workspace-write", "full-access"] | None = None


@router.get("/quota")
def get_quota(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return quota_state(db, user)


@router.get("/capabilities")
def capabilities(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    entitlement = get_user_entitlement(db, user.id)
    return {
        "capabilities": entitlement,
        "quota": quota_state(db, user),
        "models": agent_model_options(db, user),
        # The skill catalog, in the shape the DeepSeek Harness client asks for
        # (`skills/list`): name, description and the two invocation flags.
        "skills": agent_skill_catalog(),
    }


@router.post("/quote")
def agent_quote(payload: AgentQuoteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return quote_agent_run(db, user, payload.content, context={
            "research_mode": payload.research_mode,
            "data_sources": payload.data_sources,
            "skills": payload.skills,
            "skill_refs": payload.skill_refs,
            "custom_prompt": payload.custom_prompt,
            "attachments": payload.attachments,
            "model": payload.model,
            "permission_mode": payload.permission_mode,
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
    pending = db.query(AgentToolCall).join(AgentRun, AgentRun.id == AgentToolCall.run_id).filter(
        AgentRun.conversation_id == row.id, AgentRun.user_id == user.id, AgentRun.status == "running",
        AgentToolCall.status == "awaiting_approval", AgentToolCall.approval.is_(None),
        AgentToolCall.approval_expires_at > utcnow()).all()
    return {"conversation": serialize_conversation(row), "messages": [serialize_message(db, item) for item in messages],
            "pending_approvals": [{"toolCallId": call.id, "tool": call.tool_name, "arguments": call.arguments_json, "expiresAt": call.approval_expires_at.isoformat()} for call in pending]}


@router.patch("/conversations/{conversation_id}")
def update_conversation(conversation_id: str, payload: ConversationPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = owned_conversation(db, user, conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    row = db.query(AgentConversation).filter_by(id=row.id, user_id=user.id).with_for_update().one()
    if payload.permission_mode is not None:
        if payload.permission_mode == "full-access" and not payload.acknowledge_full_access:
            raise HTTPException(status_code=400, detail="FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED")
        if db.query(AgentRun).filter(AgentRun.conversation_id == row.id, AgentRun.status.in_(["pending", "running"])).count():
            raise HTTPException(status_code=409, detail="CONVERSATION_BUSY")
        row.permission_mode = permission_mode(payload.permission_mode)
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
    # Free the uploaded bytes this conversation had sent before its messages stop
    # being reachable: they would otherwise sit against the user's quota forever.
    freed = release_conversation_attachments(db, user.id, row.id)
    row.status = "deleted"
    row.archived_at = utcnow()
    db.commit()
    return {"ok": True, "attachments_released": freed}


@router.delete("/conversations")
def delete_all_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    # Materialise the ids before releasing anything: the release helper commits,
    # and iterating a query that a commit can expire is how a loop silently
    # stops halfway through.
    doomed = [row[0] for row in db.query(AgentConversation.id).filter(
        AgentConversation.user_id == user.id,
        AgentConversation.status != "deleted",
    ).all()]
    released = sum(release_conversation_attachments(db, user.id, conversation_id) for conversation_id in doomed)
    count = db.query(AgentConversation).filter(
        AgentConversation.user_id == user.id,
        AgentConversation.status != "deleted"
    ).update({"status": "deleted", "archived_at": utcnow()}, synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": count, "attachments_released": released}


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    owned_conversation(db, user, conversation_id)
    rows = db.query(AgentMessage).filter_by(conversation_id=conversation_id, user_id=user.id).order_by(AgentMessage.created_at).all()
    return {"messages": [serialize_message(db, row) for row in rows]}


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, payload: MessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> StreamingResponse:
    try:
        row = owned_conversation(db, user, conversation_id)
        run = start_run(db, user, row, payload.content, context={"research_mode": payload.research_mode, "data_sources": payload.data_sources, "skills": payload.skills, "skill_refs": payload.skill_refs, "custom_prompt": payload.custom_prompt, "attachments": payload.attachments, "model": payload.model, "permission_mode": row.permission_mode})
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
    supplied = bool(payload.data_sources or payload.skills or payload.skill_refs or payload.custom_prompt or payload.attachments or payload.model or not payload.research_mode)
    context = {"research_mode": payload.research_mode, "data_sources": payload.data_sources, "skills": payload.skills, "skill_refs": payload.skill_refs, "custom_prompt": payload.custom_prompt, "attachments": payload.attachments, "model": payload.model, "permission_mode": conversation.permission_mode} if supplied else (previous.context_json or {})
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


@router.get("/workspace-capabilities")
def workspace_capabilities(user: User = Depends(get_current_user)) -> dict:
    return {"permission_modes": ["read-only", "workspace-write", "full-access"],
            "default_permission_mode": "workspace-write", "max_file_bytes": MAX_FILE_BYTES,
            "max_files": MAX_FILES, "storage_bytes": MAX_USER_BYTES,
            "file_types": ["txt", "md", "csv", "tsv", "json", "log", "py", "js", "ts", "yaml", "yml", "pdf", "docx", "png", "jpg", "jpeg", "webp", "gif"],
            "scope": "user-owned PureGamma tools; account, plan and trading controls always apply"}


@router.post("/attachments")
async def upload_attachment(request: Request, name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="ATTACHMENT_SIZE_LIMIT")
    try:
        result = await run_in_threadpool(save_attachment, db, user, name, bytes(chunks))
        return {"attachment": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) if str(exc).startswith("ATTACHMENT_") else "ATTACHMENT_INVALID") from exc


@router.get("/attachments/{attachment_id}/content")
def attachment_content(attachment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    import hashlib
    try:
        row = owned_attachment(db, user.id, attachment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="ATTACHMENT_NOT_FOUND") from exc
    if not row.payload:
        # Removed by its owner: the bytes are gone, and saying so beats a 409
        # "integrity error" for a file that was deliberately deleted.
        raise HTTPException(status_code=410, detail="ATTACHMENT_REMOVED")
    if hashlib.sha256(row.payload).hexdigest() != row.sha256:
        raise HTTPException(status_code=409, detail="ATTACHMENT_INTEGRITY_ERROR")
    disposition = "inline" if row.kind == "image" else "attachment"
    return Response(row.payload, media_type=row.mime, headers={
        "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(row.name, safe=""),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Free the bytes of one of the caller's own attachments.

    Quota is measured in stored bytes and nothing else releases them, so without
    this a user who reached the ceiling could never upload again.
    """
    try:
        result = remove_attachment(db, user.id, attachment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="ATTACHMENT_NOT_FOUND") from exc
    return {"attachment": result}


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "denied"]


@router.post("/tool-calls/{call_id}/approval")
def approve_tool(call_id: str, payload: ApprovalRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    call = db.query(AgentToolCall).join(AgentRun, AgentRun.id == AgentToolCall.run_id).filter(
        AgentToolCall.id == call_id, AgentRun.user_id == user.id).with_for_update().one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="TOOL_CALL_NOT_FOUND")
    run = db.get(AgentRun, call.run_id)
    from datetime import timezone
    expires = call.approval_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if call.status != "awaiting_approval" or call.approval is not None or not expires or expires <= utcnow() or run.status != "running":
        raise HTTPException(status_code=409, detail="APPROVAL_NO_LONGER_PENDING")
    call.approval = payload.decision
    db.commit()
    return {"id": call.id, "decision": call.approval}
