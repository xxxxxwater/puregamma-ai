"""Signed inbound iMessage bridge for the self-hosted macOS relay."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_db
from apps.api.services.agent_service import (
    AgentLimitError,
    AgentModelInvalidError,
    AgentModelPlanError,
    AgentModelUnavailableError,
    create_conversation,
    start_run,
    stream_run,
)
from apps.api.services import imessage_voice_service
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.imessage_verification_service import normalize_e164
from apps.api.services.imessage_voice_service import (
    TranscriptionUnavailable,
    VoiceSynthesisUnavailable,
)
from packages.database.models import AgentConversation, AgentMessage, IMessageInboundEvent, User, UserPreference
from packages.skills.registry import SkillResolutionError


router = APIRouter(prefix="/internal/imessage", tags=["internal-imessage"], include_in_schema=False)

SUBSCRIPTION_REPLY = (
    "PureGamma AI: Your current plan or remaining credits do not support an iMessage Agent reply. "
    "Visit https://puregamma.ai to subscribe or add credits."
)
UNVERIFIED_REPLY = (
    ""
)
TEMPORARY_REPLY = "PureGamma AI: The Agent is temporarily unavailable. Please try again shortly."


class InboundMessage(BaseModel):
    message_id: str = Field(min_length=1, max_length=128)
    sender: str = Field(min_length=8, max_length=32)
    # Text path stays as-is; voice messages carry audio_base64 + audio_mime
    # (backward compatible: text-only payloads keep working unchanged).
    content: str = Field(default="", max_length=3000)
    audio_base64: str | None = Field(default=None)
    audio_mime: str | None = Field(default=None)


def _signature(timestamp: str, body: bytes) -> str:
    secret = get_settings().imessage_relay_secret
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def _verify(timestamp: str | None, signature: str | None, body: bytes) -> bool:
    if not timestamp or not signature or not get_settings().imessage_relay_secret:
        return False
    try:
        received_at = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - received_at) > get_settings().imessage_replay_tolerance_seconds:
        return False
    return hmac.compare_digest(_signature(timestamp, body), signature)


def _reply_text(content: str) -> str:
    content = content.strip()
    if len(content) <= 2800:
        return content
    return content[:2700].rstrip() + "\n\nFull conversation: https://puregamma.ai"


def _conversation(db: Session, user: User) -> AgentConversation:
    row = (
        db.query(AgentConversation)
        .filter_by(user_id=user.id, title="iMessage Agent", status="active")
        .order_by(AgentConversation.updated_at.desc())
        .first()
    )
    return row or create_conversation(db, user, "iMessage Agent")


def _duplicate_reply(db: Session, message_id: str) -> str | None:
    event = db.query(IMessageInboundEvent).filter_by(relay_message_id=message_id).one_or_none()
    if not event:
        return None
    assistant = db.get(AgentMessage, event.assistant_message_id) if event.assistant_message_id else None
    return _reply_text(assistant.content) if assistant and assistant.status == "completed" else ""


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def _voice_inbound(db: Session, user: User, preference: UserPreference, payload: InboundMessage) -> dict:
    """Voice message: STT -> the same main-agent answer chain as the user's
    iMessage text thread (fast-path included) -> TTS. Falls back to a text-only
    reply when transcription or synthesis is unavailable."""
    locale = preference.locale or "en"
    try:
        audio, extension = imessage_voice_service.decode_audio(payload.audio_base64 or "", payload.audio_mime)
    except TranscriptionUnavailable as exc:
        return {"reply": f"PureGamma AI: I could not read that voice message ({exc}). Please try again or send text.", "status": "failed"}
    try:
        text = imessage_voice_service.transcribe_audio(db, user, audio, extension, locale)
    except InsufficientCreditsError:
        db.rollback()
        return {"reply": SUBSCRIPTION_REPLY, "status": "subscription_required"}
    except TranscriptionUnavailable as exc:
        return {"reply": f"PureGamma AI: I could not transcribe that voice message ({exc}). Please try again or send text.", "status": "failed"}
    event = IMessageInboundEvent(relay_message_id=payload.message_id, user_id=user.id)
    db.add(event)
    db.flush()
    try:
        run = start_run(
            db,
            user,
            _conversation(db, user),
            text,
            context={"imessage_source_id": payload.message_id, "channel": "imessage", "input_modality": "voice"},
        )
        for _ in stream_run(db, user, run.id, locale):
            pass
    except (
        InsufficientCreditsError,
        AgentLimitError,
        AgentModelPlanError,
        AgentModelUnavailableError,
        SkillResolutionError,
    ):
        db.rollback()
        return {"reply": SUBSCRIPTION_REPLY, "status": "subscription_required"}
    except (AgentModelInvalidError, ValueError):
        db.rollback()
        return {"reply": TEMPORARY_REPLY, "status": "failed"}
    assistant = db.get(AgentMessage, run.assistant_message_id)
    if not assistant or assistant.status != "completed":
        event.status = "failed"
        db.commit()
        return {"reply": TEMPORARY_REPLY, "status": "failed"}
    reply_text = _reply_text(assistant.content)
    event.status = "completed"
    event.assistant_message_id = assistant.id
    try:
        reply_audio = imessage_voice_service.synthesize_voice(db, user, reply_text, locale)
    except (VoiceSynthesisUnavailable, InsufficientCreditsError):
        # TTS is best-effort: the completed answer still goes out as text.
        db.commit()
        return {"reply": reply_text, "status": "completed", "reply_text": reply_text}
    db.commit()
    return {
        "reply": reply_text,
        "status": "completed",
        "reply_text": reply_text,
        "reply_audio_base64": base64.b64encode(reply_audio).decode(),
        "reply_audio_mime": "audio/mpeg",
    }


@router.post("/inbound")
def inbound(
    body: bytes = Depends(_raw_body),
    db: Session = Depends(get_db),
    x_pg_timestamp: str | None = Header(default=None, alias="X-PG-Timestamp"),
    x_pg_signature: str | None = Header(default=None, alias="X-PG-Signature"),
) -> dict:
    if not _verify(x_pg_timestamp, x_pg_signature, body):
        raise HTTPException(status_code=401, detail="invalid_hmac_signature")
    payload = InboundMessage(**json.loads(body.decode()))
    try:
        sender = normalize_e164(payload.sender)
    except ValueError:
        return {"reply": UNVERIFIED_REPLY, "status": "unverified"}
    preferences = (
        db.query(UserPreference)
        .filter(
            UserPreference.imessage_recipient == sender,
            UserPreference.imessage_recipient_verified_at.is_not(None),
        )
        .limit(2)
        .all()
    )
    if len(preferences) != 1:
        return {"reply": UNVERIFIED_REPLY, "status": "unverified"}
    preference = preferences[0]
    user = db.get(User, preference.user_id)
    if not user:
        return {"reply": UNVERIFIED_REPLY, "status": "unverified"}
    duplicate = _duplicate_reply(db, payload.message_id)
    if duplicate is not None:
        return {"reply": duplicate, "status": "duplicate"}
    if payload.audio_base64:
        return _voice_inbound(db, user, preference, payload)
    if not payload.content.strip():
        return {"reply": TEMPORARY_REPLY, "status": "failed"}
    try:
        event = IMessageInboundEvent(relay_message_id=payload.message_id, user_id=user.id)
        db.add(event)
        db.flush()
        run = start_run(
            db,
            user,
            _conversation(db, user),
            payload.content,
            context={"imessage_source_id": payload.message_id, "channel": "imessage"},
        )
        for _ in stream_run(db, user, run.id, preference.locale):
            pass
        assistant = db.get(AgentMessage, run.assistant_message_id)
        if not assistant or assistant.status != "completed":
            event.status = "failed"
            db.commit()
            return {"reply": TEMPORARY_REPLY, "status": "failed"}
        event.status = "completed"
        event.assistant_message_id = assistant.id
        db.commit()
        return {"reply": _reply_text(assistant.content), "status": "completed"}
    except (
        InsufficientCreditsError,
        AgentLimitError,
        AgentModelPlanError,
        AgentModelUnavailableError,
        SkillResolutionError,
    ):
        db.rollback()
        return {"reply": SUBSCRIPTION_REPLY, "status": "subscription_required"}
    except (AgentModelInvalidError, ValueError):
        db.rollback()
        return {"reply": TEMPORARY_REPLY, "status": "failed"}
