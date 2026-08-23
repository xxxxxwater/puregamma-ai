"""Signed inbound iMessage bridge for the self-hosted macOS relay."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
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
from packages.notifications.imessage.webhook_gateway import verify_photon_signature
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
    sender: str = Field(min_length=3, max_length=64)
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


def resolve_verified_user(db: Session, sender_raw: str) -> tuple[str, UserPreference, User] | None:
    """Normalize a sender and resolve the single verified user bound to it.

    Returns (normalized_sender, preference, user) or None when the sender is
    not a verified iMessage recipient. Shared by the inbound flow and the
    Photon worker so both use exactly the same matching rules."""
    try:
        sender = normalize_e164(sender_raw)
    except ValueError:
        return None
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
        return None
    user = db.get(User, preferences[0].user_id)
    if not user:
        return None
    return sender, preferences[0], user


def _process_inbound(db: Session, payload: InboundMessage) -> dict:
    """Shared inbound business flow: sender normalization, verified-user
    matching, IMessageInboundEvent dedupe, agent reply, billing and limits.
    Used by the Mac relay route (synchronously) and by the Photon worker
    (inside a Celery task) so neither path duplicates the business logic."""
    resolved = resolve_verified_user(db, payload.sender)
    if not resolved:
        return {"reply": UNVERIFIED_REPLY, "status": "unverified"}
    sender, preference, user = resolved
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


@router.post("/inbound")
def inbound(
    body: bytes = Depends(_raw_body),
    db: Session = Depends(get_db),
    x_pg_timestamp: str | None = Header(default=None, alias="X-PG-Timestamp"),
    x_pg_signature: str | None = Header(default=None, alias="X-PG-Signature"),
) -> dict:
    """Mac relay inbound. Signing protocol (X-PG-*) unchanged."""
    if not _verify(x_pg_timestamp, x_pg_signature, body):
        raise HTTPException(status_code=401, detail="invalid_hmac_signature")
    payload = InboundMessage(**json.loads(body.decode()))
    return _process_inbound(db, payload)


def _photon_line_matches(settings, raw: dict) -> tuple[bool, str]:
    """Check the webhook line identifier against PHOTON_LINE_ID when set.
    PHOTON_LINE_ID selects the allowed inbound line; it is NOT a credential."""
    configured = (settings.photon_line_id or "").strip()
    if not configured:
        return True, ""
    space = raw.get("space") if isinstance(raw.get("space"), dict) else {}
    message = raw.get("message") if isinstance(raw.get("message"), dict) else {}
    line = message.get("line") if isinstance(message.get("line"), dict) else {}
    candidates = {
        str(space.get("id") or ""),
        str(space.get("phone") or ""),
        str(space.get("line_id") or ""),
        str(line.get("id") or ""),
        str(line.get("phone") or ""),
    }
    candidates.discard("")
    if configured in candidates:
        return True, ""
    # Diagnostic carries no identifier values: line ids are PII-ish metadata.
    return False, "line_mismatch"


@router.post("/photon/webhook")
def photon_webhook(
    body: bytes = Depends(_raw_body),
    db: Session = Depends(get_db),
    x_spectrum_timestamp: str | None = Header(default=None, alias="X-Spectrum-Timestamp"),
    x_spectrum_signature: str | None = Header(default=None, alias="X-Spectrum-Signature"),
    x_spectrum_event: str | None = Header(default=None, alias="X-Spectrum-Event"),
) -> dict:
    """Photon inbound webhook.

    Verifies the X-Spectrum signature (HMAC-SHA256 over v0:{timestamp}:{raw
    body} with PHOTON_WEBHOOK_SECRET), a five-minute replay window, the
    X-Spectrum-Event header and the payload event/line, then persists the
    pending event and enqueues a Celery task before returning 2xx. The worker
    later runs the shared agent flow and sends the reply through
    PhotonIMessageProvider; the webhook never waits on the LLM.

    Unknown events, non-text content types and own outbound echoes are
    acknowledged with 2xx diagnostics instead of being processed. Non-text
    attachments are NOT processed: inbound media requires the Photon
    SDK/Proxy attachment download capability, which the webhook body does
    not carry."""
    settings = get_settings()
    if not verify_photon_signature(
        settings.photon_webhook_secret,
        x_spectrum_timestamp or "",
        body,
        x_spectrum_signature or "",
    ):
        raise HTTPException(status_code=401, detail="invalid_photon_signature")
    event_name = (x_spectrum_event or "").strip().lower()
    if event_name != "messages":
        return {"status": "ignored", "reason": f"unsupported_event:{event_name or 'missing'}"}
    try:
        raw = json.loads(body.decode())
    except (ValueError, UnicodeDecodeError):
        return {"status": "ignored", "reason": "invalid_json"}
    if str(raw.get("event") or "").lower() != "messages":
        return {"status": "ignored", "reason": "unsupported_payload_event"}
    line_ok, line_reason = _photon_line_matches(settings, raw)
    if not line_ok:
        return {"status": "ignored", "reason": line_reason}
    message = raw.get("message")
    if not isinstance(message, dict):
        return {"status": "ignored", "reason": "missing_message"}
    direction = str(message.get("direction") or "")
    platform = str(message.get("platform") or "")
    if direction != "inbound" or platform.lower() != "imessage":
        return {
            "status": "ignored",
            "reason": "not_inbound_imessage",
            "diagnostics": {"direction": direction, "platform": platform},
        }
    content = message.get("content") if isinstance(message.get("content"), dict) else {}
    content_type = str(content.get("type") or "")
    message_id = str(message.get("id") or "")
    if content_type != "text":
        # Acknowledge attachments but do not pretend to process them: the
        # webhook carries no attachment bytes. Media inbound must use the
        # Photon SDK/Proxy download capability at a later phase.
        return {
            "status": "unprocessed",
            "reason": f"unsupported_content_type:{content_type or 'missing'}",
            "diagnostics": {"message_id": message_id},
        }
    sender_raw = message.get("sender") if isinstance(message.get("sender"), dict) else {}
    sender_id = str(sender_raw.get("id") or "")
    text = content.get("text")
    if not message_id or not sender_id or not isinstance(text, str) or not text.strip():
        return {"status": "ignored", "reason": "missing_message_fields"}
    try:
        payload = InboundMessage(message_id=message_id, sender=sender_id, content=text)
    except ValidationError:
        return {"status": "ignored", "reason": "invalid_message_shape"}
    # Fast acknowledge: persist the pending event and enqueue a Celery task.
    # The agent/LLM run happens in the worker; Photon only needs a quick 2xx.
    # (Lazy import keeps the router module free of a service -> router cycle.)
    from apps.api.services.photon_inbound_service import enqueue_photon_inbound

    return enqueue_photon_inbound(
        db,
        message_id=payload.message_id,
        sender=payload.sender,
        content=payload.content,
    )
