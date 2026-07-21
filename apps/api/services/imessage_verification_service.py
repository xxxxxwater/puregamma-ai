from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import DailyBriefPreference, IMessageVerificationChallenge, NotificationDelivery, User, UserPreference, utcnow
from packages.notifications.imessage.macos_relay_client import MacOSIMessageRelayClient
from packages.notifications.imessage.mock_provider import MockIMessageProvider


E164 = re.compile(r"^\+[1-9]\d{7,14}$")
IMESSAGE_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class VerificationRateLimitError(RuntimeError):
    pass


def normalize_e164(value: str) -> str:
    """Normalize a phone number or Apple ID email usable by iMessage."""
    normalized = re.sub(r"[\s().-]", "", value.strip())
    if E164.fullmatch(normalized):
        return normalized
    email = value.strip().lower()
    if IMESSAGE_EMAIL.fullmatch(email):
        return email
    raise ValueError("INVALID_IMESSAGE_RECIPIENT")


def _hash(user_id: str, recipient: str, code: str) -> str:
    secret = get_settings().jwt_secret
    return hmac.new(secret.encode(), f"{user_id}:{recipient}:{code}".encode(), hashlib.sha256).hexdigest()


def request_verification(db: Session, user: User, recipient: str) -> dict:
    """Bind an iMessage address to the signed-in account without sending SMS/iMessage."""
    recipient = normalize_e164(recipient)
    preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none() or UserPreference(user_id=user.id)
    preference.imessage_recipient = recipient
    preference.imessage_recipient_verified_at = utcnow()
    db.add(preference)
    db.commit()
    return {"recipient": recipient, "recipient_verified_at": preference.imessage_recipient_verified_at.isoformat(), "bound": True}


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
