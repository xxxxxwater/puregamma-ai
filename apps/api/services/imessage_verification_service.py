from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import DailyBriefPreference, IMessageVerificationChallenge, NotificationDelivery, User, UserPreference, utcnow
from packages.notifications.imessage.macos_relay_client import MacOSIMessageRelayClient
from packages.notifications.imessage.mock_provider import MockIMessageProvider


E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_e164(value: str) -> str:
    normalized = re.sub(r"[\s().-]", "", value.strip())
    if not E164.fullmatch(normalized):
        raise ValueError("INVALID_E164_RECIPIENT")
    return normalized


def _hash(user_id: str, recipient: str, code: str) -> str:
    secret = get_settings().jwt_secret
    return hmac.new(secret.encode(), f"{user_id}:{recipient}:{code}".encode(), hashlib.sha256).hexdigest()


def request_verification(db: Session, user: User, recipient: str) -> dict:
    entitlement = get_user_entitlement(db, user.id)
    if not entitlement["imessage_enabled"]:
        raise PermissionError("IMESSAGE_ENTITLEMENT_DENIED")
    recipient = normalize_e164(recipient)
    preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none() or UserPreference(user_id=user.id)
    if preference.imessage_recipient != recipient:
        preference.imessage_recipient_verified_at = None
    preference.imessage_recipient = recipient
    db.add(preference)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = IMessageVerificationChallenge(user_id=user.id, recipient=recipient, code_hash=_hash(user.id, recipient, code), expires_at=utcnow() + timedelta(minutes=10))
    db.add(challenge)
    db.flush()
    settings = get_settings()
    provider = MacOSIMessageRelayClient() if settings.imessage_provider == "macos_relay" else MockIMessageProvider()
    result = provider.send(recipient, f"PureGamma AI verification code: {code}", f"imessage-verify:{challenge.id}")
    delivery = NotificationDelivery(user_id=user.id, channel="imessage", recipient=recipient, payload={"type": "verification"}, locale=preference.locale, status="sent" if result.ok else "failed_retryable", provider_response={"type": "verification", "status": result.response.get("status")}, idempotency_key=f"imessage-verify:{challenge.id}", attempt_count=1, last_attempt_at=utcnow(), next_retry_at=None if result.ok else utcnow() + timedelta(minutes=1), last_error=None if result.ok else "provider_failed", sent_at=utcnow() if result.ok else None)
    db.add(delivery)
    db.commit()
    if not result.ok:
        raise RuntimeError("VERIFICATION_DELIVERY_FAILED")
    response = {"challenge_id": challenge.id, "expires_at": challenge.expires_at.isoformat(), "recipient": recipient}
    if settings.app_environment.lower() != "production" and settings.imessage_provider == "mock":
        response["development_code"] = code
    return response


def confirm_verification(db: Session, user: User, challenge_id: str, code: str) -> dict:
    challenge = db.query(IMessageVerificationChallenge).filter_by(id=challenge_id, user_id=user.id).one_or_none()
    if not challenge:
        raise ValueError("VERIFICATION_CHALLENGE_NOT_FOUND")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        from datetime import timezone
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if challenge.verified_at or expires_at < utcnow() or challenge.attempts >= 5:
        raise ValueError("VERIFICATION_CHALLENGE_EXPIRED")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _hash(user.id, challenge.recipient, code.strip())):
        db.commit()
        raise ValueError("VERIFICATION_CODE_INVALID")
    challenge.verified_at = utcnow()
    preference = db.query(UserPreference).filter_by(user_id=user.id).one()
    preference.imessage_recipient = challenge.recipient
    preference.imessage_recipient_verified_at = challenge.verified_at
    daily = db.get(DailyBriefPreference, user.id)
    if daily and daily.channel == "imessage":
        daily.recipient = challenge.recipient
        daily.recipient_verified_at = challenge.verified_at
    db.commit()
    return {"recipient": challenge.recipient, "recipient_verified_at": challenge.verified_at.isoformat()}
