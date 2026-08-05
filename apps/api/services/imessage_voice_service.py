"""Voice pipeline for the iMessage bridge: STT -> secretary dialog -> TTS.

Reuses the same external providers and credit metering as the web secretary
surface (OpenAI transcription, noiz.ai synthesis, private_secretary_reply
quote) so iMessage voice messages behave like a secretary voice dialog.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import uuid

import requests
from sqlalchemy.orm import Session

from apps.api.services.credit_service import (
    InsufficientCreditsError,
    quote_task,
    refund_task,
    reserve_task,
    settle_task,
)
from packages.agents.llm.provider_factory import get_llm_provider
from packages.data.online_research_provider import online_research_enabled
from packages.database.models import AgentMessage, User

logger = logging.getLogger(__name__)

MIN_AUDIO_BYTES = 512
MAX_AUDIO_BYTES = 2_000_000
MAX_TTS_CHARS = 1400

_EXTENSION_BY_MIME = {
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


class TranscriptionUnavailable(RuntimeError):
    """Inbound audio could not be transcribed; code is machine-readable."""


class SecretaryDialogUnavailable(RuntimeError):
    """The secretary reply chain failed after transcription."""


class VoiceSynthesisUnavailable(RuntimeError):
    """Outbound TTS failed; callers should fall back to a text reply."""


def decode_audio(audio_base64: str, audio_mime: str | None) -> tuple[bytes, str]:
    try:
        audio = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TranscriptionUnavailable("AUDIO_DECODE_FAILED") from exc
    extension = _EXTENSION_BY_MIME.get((audio_mime or "").strip().lower())
    if not extension:
        raise TranscriptionUnavailable("UNSUPPORTED_AUDIO_FORMAT")
    if len(audio) < MIN_AUDIO_BYTES or len(audio) > MAX_AUDIO_BYTES:
        raise TranscriptionUnavailable("AUDIO_SIZE_INVALID")
    return audio, extension


def transcribe_audio(db: Session, user: User, audio: bytes, extension: str, locale: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise TranscriptionUnavailable("STT_NOT_CONFIGURED")
    quote = quote_task(task_type="secretary_transcribe", requested_model="default", attachment_bytes=len(audio))
    reservation = reserve_task(
        db,
        user.id,
        quote,
        f"imessage-transcribe:{user.id}:{uuid.uuid4()}",
        {"surface": "imessage", "action": "transcribe"},
    )
    db.commit()
    language = "zh" if locale == "zh" else "en"
    try:
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (f"imessage.{extension}", audio, f"audio/{extension}")},
            data={
                "model": os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
                "language": language,
                "response_format": "json",
                "prompt": "PureGamma private secretary conversation. Preserve names, product terms, and natural punctuation.",
            },
            timeout=120,
        )
    except requests.RequestException as exc:
        refund_task(db, user.id, reservation, "STT_UNAVAILABLE")
        db.commit()
        raise TranscriptionUnavailable("STT_UNAVAILABLE") from exc
    if response.status_code != 200:
        refund_task(db, user.id, reservation, "STT_TRANSCRIPTION_FAILED")
        db.commit()
        raise TranscriptionUnavailable("STT_TRANSCRIPTION_FAILED")
    try:
        text = str(response.json().get("text", "")).strip()
    except ValueError as exc:
        refund_task(db, user.id, reservation, "STT_INVALID_RESPONSE")
        db.commit()
        raise TranscriptionUnavailable("STT_INVALID_RESPONSE") from exc
    if not text:
        refund_task(db, user.id, reservation, "STT_EMPTY_TRANSCRIPT")
        db.commit()
        raise TranscriptionUnavailable("STT_EMPTY_TRANSCRIPT")
    settle_task(db, user.id, reservation, quote.credits, metadata={"surface": "imessage", "action": "transcribe"})
    db.commit()
    return text


def secretary_reply(db: Session, user: User, content: str, locale: str, request_id: str) -> tuple[str, str]:
    """Run the web secretary's dialog chain for an iMessage voice message.

    Mirrors apps.api.routers.secretary.create_message (history, optional
    research, metering, persistence) without the HTTP layer. Returns
    (answer, assistant_message_id).
    """
    from apps.api.routers.secretary import (  # local import avoids circularity
        _conversation,
        _prompt,
        _secretary_online_candidate,
        _secretary_quote,
        _secretary_research,
        _uses_english,
    )

    conversation = _conversation(db, user.id, create=False)
    history = [] if not conversation else (
        db.query(AgentMessage)
        .filter(
            AgentMessage.conversation_id == conversation.id,
            AgentMessage.user_id == user.id,
            AgentMessage.status == "completed",
        )
        .order_by(AgentMessage.created_at.desc())
        .limit(16)
        .all()
    )
    history.reverse()
    research_requested = online_research_enabled() and _secretary_online_candidate(content)
    quote = _secretary_quote(online_research=research_requested)
    reservation = reserve_task(
        db,
        user.id,
        quote,
        f"imessage-secretary:{user.id}:{request_id}",
        {"surface": "imessage_secretary", "request_id": request_id, "locale": locale},
    )
    db.commit()
    try:
        research_context, research_audit = _secretary_research(
            db,
            user,
            conversation.id if conversation else None,
            content,
        )
    except Exception as exc:  # research is best-effort, same as the web surface
        logger.warning("imessage secretary research failed: %s", type(exc).__name__)
        research_context = (
            "Current-source lookup is temporarily unavailable. If the answer depends on current facts, "
            "state that live evidence could not be verified and do not fill the gap from memory."
        )
        research_audit = {"attempted": research_requested, "online_used": False, "status": "unavailable", "tools": [], "errors": [f"research_runtime:{type(exc).__name__}"]}
    try:
        answer = get_llm_provider().complete(
            _prompt(locale, history, content, research_context),
            task_type="secretary_dialog",
            locale=locale,
            user_id=user.id,
            db=db,
        ).strip()
    except Exception as exc:
        db.rollback()
        refund_task(db, user.id, reservation, "SECRETARY_MODEL_UNAVAILABLE", {"request_id": request_id})
        db.commit()
        raise SecretaryDialogUnavailable("SECRETARY_MODEL_UNAVAILABLE") from exc
    if not answer:
        db.rollback()
        refund_task(db, user.id, reservation, "SECRETARY_EMPTY_RESPONSE", {"request_id": request_id})
        db.commit()
        raise SecretaryDialogUnavailable("SECRETARY_EMPTY_RESPONSE")
    try:
        conversation = conversation or _conversation(db, user.id)
        reply_locale = "en" if _uses_english(locale, content) else "zh"
        user_message = AgentMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=content,
            status="completed",
            input_tokens=max(1, len(content) // 4),
            context_json={"surface": "imessage_secretary", "locale": locale, "request_id": request_id, "channel": "imessage_voice"},
        )
        assistant_message = AgentMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            content=answer,
            status="completed",
            output_tokens=max(1, len(answer) // 4),
            context_json={"surface": "imessage_secretary", "locale": reply_locale, "request_id": request_id, "channel": "imessage_voice", "research": research_audit},
        )
        from datetime import datetime, timezone

        conversation.updated_at = datetime.now(timezone.utc)
        db.add_all([user_message, assistant_message])
        settle_task(db, user.id, reservation, quote.credits, {"request_id": request_id})
        db.commit()
        db.refresh(assistant_message)
    except Exception as exc:
        db.rollback()
        refund_task(db, user.id, reservation, "SECRETARY_PERSISTENCE_FAILED", {"request_id": request_id})
        db.commit()
        raise SecretaryDialogUnavailable("SECRETARY_PERSISTENCE_FAILED") from exc
    return answer, assistant_message.id


def synthesize_voice(db: Session, user: User, text: str, locale: str) -> bytes:
    """Turn a secretary reply into mp3 bytes via the noiz.ai secretary voice."""
    from apps.api.routers.secretary import DEFAULT_ENGLISH_VOICE_ID, _normalized_key, _voice_id

    api_key = os.getenv("NOIZ_API_KEY", "").strip()
    if not api_key:
        raise VoiceSynthesisUnavailable("NOIZ_NOT_CONFIGURED")
    text = text.strip()[:MAX_TTS_CHARS]
    if not text:
        raise VoiceSynthesisUnavailable("EMPTY_TEXT")
    quote = quote_task(task_type="secretary_voice", requested_model="default", input_tokens=max(1, len(text) // 4))
    try:
        reservation = reserve_task(
            db,
            user.id,
            quote,
            f"imessage-voice:{user.id}:{uuid.uuid4()}",
            {"surface": "imessage", "action": "voice"},
        )
        db.commit()
    except InsufficientCreditsError as exc:
        db.rollback()
        raise VoiceSynthesisUnavailable("INSUFFICIENT_CREDITS") from exc
    voice_id = _voice_id(locale, text)
    english = voice_id == os.getenv("NOIZ_ENGLISH_VOICE_ID", DEFAULT_ENGLISH_VOICE_ID)
    try:
        response = requests.post(
            "https://noiz.ai/v1/text-to-speech",
            headers={"Authorization": _normalized_key(api_key)},
            data={
                "text": text,
                "voice_id": voice_id,
                "output_format": "mp3",
                "speed": "0.96",
                "target_lang": "en-us" if english else "zh",
            },
            timeout=120,
        )
    except requests.RequestException as exc:
        refund_task(db, user.id, reservation, "NOIZ_UNAVAILABLE")
        db.commit()
        raise VoiceSynthesisUnavailable("NOIZ_UNAVAILABLE") from exc
    if response.status_code != 200 or not response.content:
        refund_task(db, user.id, reservation, "NOIZ_SYNTHESIS_FAILED")
        db.commit()
        raise VoiceSynthesisUnavailable("NOIZ_SYNTHESIS_FAILED")
    settle_task(db, user.id, reservation, quote.credits, metadata={"surface": "imessage", "action": "voice"})
    db.commit()
    return response.content
