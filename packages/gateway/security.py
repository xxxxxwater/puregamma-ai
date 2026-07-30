from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import GatewayApiKey, GatewayIPBlock, GatewaySecurityEvent, User


MAX_API_KEYS_PER_USER = 10


def client_ip(request: Request) -> str:
    # Caddy sets X-Real-IP and does not expose client-controlled forwarded
    # headers to the API container. Do not trust X-Forwarded-For here.
    return (request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown"))[:64]


def _key_pepper() -> bytes:
    settings = get_settings()
    # Development needs deterministic local tests; production validation
    # requires GATEWAY_API_KEY_PEPPER to be a dedicated strong secret.
    return (settings.gateway_api_key_pepper or settings.jwt_secret).encode("utf-8")


def key_hint(raw_key: str) -> str:
    return raw_key[:18]


def hash_api_key(raw_key: str) -> str:
    return hmac.new(_key_pepper(), raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_gateway_entitlement(db: Session, user: User) -> None:
    if user.plan not in {"Pro", "Max", "Enterprise"}:
        raise HTTPException(status_code=403, detail={"code": "GATEWAY_PAID_PLAN_REQUIRED"})
    from apps.api.services.billing_service import current_subscription

    settings = get_settings()
    if settings.app_environment.lower() == "production" and settings.billing_mode == "stripe":
        subscription = current_subscription(db, user.id)
        if not subscription or subscription.status not in {"active", "trialing"}:
            raise HTTPException(status_code=403, detail={"code": "GATEWAY_SUBSCRIPTION_INACTIVE"})


def create_api_key(
    db: Session,
    user: User,
    *,
    name: str,
    rate_limit_rpm: int | None = None,
    scopes: list[str] | None = None,
    rotated_from_key_id: str | None = None,
) -> tuple[GatewayApiKey, str]:
    _ensure_gateway_entitlement(db, user)
    active_or_paused = (
        db.query(GatewayApiKey)
        .filter(GatewayApiKey.user_id == user.id, GatewayApiKey.status.in_(("active", "paused")))
        .count()
    )
    if active_or_paused >= MAX_API_KEYS_PER_USER:
        raise HTTPException(status_code=409, detail={"code": "GATEWAY_API_KEY_LIMIT", "limit": MAX_API_KEYS_PER_USER})
    settings = get_settings()
    raw_key = f"sk-pg-{secrets.token_urlsafe(30)}"
    row = GatewayApiKey(
        user_id=user.id,
        name=name.strip()[:80] or "Default key",
        key_hint=key_hint(raw_key),
        key_hash=hash_api_key(raw_key),
        last_four=raw_key[-4:],
        status="active",
        rate_limit_rpm=rate_limit_rpm or settings.gateway_default_rate_limit_rpm,
        scopes_json=scopes or ["chat"],
        rotated_from_key_id=rotated_from_key_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw_key


def serialize_api_key(row: GatewayApiKey) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.key_hint,
        "last_four": row.last_four,
        "status": row.status,
        "rate_limit_rpm": row.rate_limit_rpm,
        "scopes": row.scopes_json,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat(),
    }


def list_api_keys(db: Session, user_id: str) -> list[GatewayApiKey]:
    return (
        db.query(GatewayApiKey)
        .filter_by(user_id=user_id)
        .order_by(GatewayApiKey.created_at.desc())
        .all()
    )


def set_api_key_status(db: Session, user_id: str, key_id: str, status: str) -> GatewayApiKey:
    if status not in {"active", "paused", "revoked"}:
        raise ValueError("GATEWAY_KEY_STATUS_INVALID")
    row = db.query(GatewayApiKey).filter_by(id=key_id, user_id=user_id).one_or_none()
    if not row:
        raise ValueError("GATEWAY_API_KEY_NOT_FOUND")
    row.status = status
    row.revoked_at = _now() if status == "revoked" else None
    db.commit()
    db.refresh(row)
    return row


def rotate_api_key(db: Session, user: User, key_id: str) -> tuple[GatewayApiKey, str]:
    previous = db.query(GatewayApiKey).filter_by(id=key_id, user_id=user.id).one_or_none()
    if not previous or previous.status == "revoked":
        raise ValueError("GATEWAY_API_KEY_NOT_FOUND")
    previous.status = "revoked"
    previous.revoked_at = _now()
    db.flush()
    # Rotation replaces an existing key rather than consuming an extra slot.
    return create_api_key(
        db,
        user,
        name=previous.name,
        rate_limit_rpm=previous.rate_limit_rpm,
        scopes=list(previous.scopes_json or ["chat"]),
        rotated_from_key_id=previous.id,
    )


def _security_event(db: Session, event_type: str, *, api_key: GatewayApiKey | None, ip_address: str, metadata: dict[str, Any] | None = None) -> None:
    db.add(
        GatewaySecurityEvent(
            user_id=api_key.user_id if api_key else None,
            api_key_id=api_key.id if api_key else None,
            event_type=event_type,
            severity="warning",
            ip_address=ip_address,
            metadata_json=metadata or {},
        )
    )


def authenticate_api_key(db: Session, raw_key: str, request: Request) -> GatewayApiKey:
    if not raw_key.startswith("sk-pg-") or len(raw_key) < 24:
        raise HTTPException(status_code=401, detail={"code": "GATEWAY_INVALID_API_KEY"})
    candidates = db.query(GatewayApiKey).filter_by(key_hint=key_hint(raw_key)).all()
    digest = hash_api_key(raw_key)
    row = next((item for item in candidates if hmac.compare_digest(item.key_hash, digest)), None)
    if not row or row.status != "active":
        raise HTTPException(status_code=401, detail={"code": "GATEWAY_INVALID_API_KEY"})
    blocked = (
        db.query(GatewayIPBlock)
        .filter_by(ip_address=client_ip(request), active=True)
        .order_by(GatewayIPBlock.created_at.desc())
        .first()
    )
    if blocked and (blocked.expires_at is None or blocked.expires_at > _now()):
        _security_event(db, "ip_blocked", api_key=row, ip_address=client_ip(request))
        db.commit()
        raise HTTPException(status_code=403, detail={"code": "GATEWAY_IP_BLOCKED"})
    _rate_limit(db, row, request)
    row.last_used_at = _now()
    db.commit()
    return row


def _rate_limit(db: Session, api_key: GatewayApiKey, request: Request) -> None:
    settings = get_settings()
    minute_key = int(_now().timestamp() // 60)
    redis_key = f"pg:gateway:rate:{api_key.id}:{minute_key}"
    try:
        from apps.api.redis_client import get_redis

        redis = get_redis()
        count = int(redis.incr(redis_key))
        if count == 1:
            redis.expire(redis_key, 120)
        if count > api_key.rate_limit_rpm:
            _security_event(db, "rate_limit_exceeded", api_key=api_key, ip_address=client_ip(request), metadata={"rpm": api_key.rate_limit_rpm})
            db.commit()
            raise HTTPException(status_code=429, detail={"code": "GATEWAY_RATE_LIMITED"}, headers={"Retry-After": "60"})
    except HTTPException:
        raise
    except Exception as exc:
        if settings.app_environment.lower() == "production":
            raise HTTPException(status_code=503, detail={"code": "GATEWAY_RATE_LIMIT_UNAVAILABLE"}) from exc
