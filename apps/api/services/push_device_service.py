from __future__ import annotations

import hashlib
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.config.secret_store import SecretStore
from packages.database.models import PushDevice, User, utcnow


TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64,200}$")


def _store() -> SecretStore:
    key = hashlib.sha256(get_settings().encryption_master_key.encode()).digest()
    return SecretStore(key)


def normalize_token(value: str) -> str:
    token = value.strip().lower().replace(" ", "").replace("<", "").replace(">", "")
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("INVALID_APNS_DEVICE_TOKEN")
    return token


def register_device(
    db: Session,
    user: User,
    *,
    token: str,
    environment: str,
    locale: str,
    timezone_name: str,
) -> PushDevice:
    normalized = normalize_token(token)
    if environment not in {"sandbox", "production"}:
        raise ValueError("INVALID_APNS_ENVIRONMENT")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("INVALID_TIMEZONE") from exc
    token_hash = hashlib.sha256(normalized.encode()).hexdigest()
    row = db.query(PushDevice).filter_by(token_hash=token_hash).one_or_none()
    ciphertext = _store().encrypt(normalized, metadata={"platform": "ios", "environment": environment})
    if not row:
        row = PushDevice(user_id=user.id, token_hash=token_hash, token_ciphertext=ciphertext)
        db.add(row)
    row.user_id = user.id
    row.token_ciphertext = ciphertext
    row.platform = "ios"
    row.environment = environment
    row.locale = "zh" if locale.lower().startswith("zh") else "en"
    row.timezone = timezone_name
    row.enabled = True
    row.last_seen_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def unregister_device(db: Session, user: User, token: str) -> bool:
    normalized = normalize_token(token)
    token_hash = hashlib.sha256(normalized.encode()).hexdigest()
    row = db.query(PushDevice).filter_by(token_hash=token_hash, user_id=user.id).one_or_none()
    if not row:
        return False
    row.enabled = False
    db.commit()
    return True


def decrypt_device_token(row: PushDevice) -> str:
    return _store().decrypt(row.token_ciphertext)


def serialize_device(row: PushDevice) -> dict:
    return {
        "id": row.id,
        "token_hash": row.token_hash,
        "platform": row.platform,
        "environment": row.environment,
        "locale": row.locale,
        "timezone": row.timezone,
        "enabled": row.enabled,
        "last_seen_at": row.last_seen_at.isoformat(),
    }
