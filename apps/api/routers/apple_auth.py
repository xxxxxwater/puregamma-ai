from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import Settings, get_settings
from apps.api.dependencies import create_access_token, get_db
from apps.api.routers.auth import serialize_user
from apps.api.routers.google_auth import _email_verified, _should_update_name
from packages.config.secret_store import SecretStore
from packages.database.models import UsageEvent, User, UserIdentity, UserPreference


router = APIRouter(prefix="/auth/mobile", tags=["auth"])
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = f"{APPLE_ISSUER}/auth/keys"
APPLE_TOKEN_URL = f"{APPLE_ISSUER}/auth/token"
APPLE_REVOKE_URL = f"{APPLE_ISSUER}/auth/revoke"
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


class AppleExchangeRequest(BaseModel):
    identity_token: str = Field(min_length=64, max_length=16_384)
    authorization_code: str = Field(min_length=8, max_length=4_096)
    nonce: str = Field(min_length=32, max_length=256)
    given_name: str | None = Field(default=None, max_length=120)
    family_name: str | None = Field(default=None, max_length=120)


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _json_segment(value: dict) -> str:
    return _b64encode(json.dumps(value, separators=(",", ":")).encode())


def _apple_nonce(raw_nonce: str) -> str:
    return hashlib.sha256(raw_nonce.encode()).hexdigest()


def _apple_jwks() -> list[dict]:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(APPLE_KEYS_URL)
        response.raise_for_status()
        return list(response.json().get("keys", []))


def _verify_apple_identity_token(identity_token: str, nonce: str, settings: Settings) -> dict:
    try:
        header_raw, payload_raw, signature_raw = identity_token.split(".")
        header = json.loads(_b64decode(header_raw))
        claims = json.loads(_b64decode(payload_raw))
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise ValueError("Unsupported Apple token algorithm")
        key = next(item for item in _apple_jwks() if item.get("kid") == header["kid"] and item.get("kty") == "RSA")
        public_key = rsa.RSAPublicNumbers(
            int.from_bytes(_b64decode(key["e"]), "big"),
            int.from_bytes(_b64decode(key["n"]), "big"),
        ).public_key()
        public_key.verify(_b64decode(signature_raw), f"{header_raw}.{payload_raw}".encode(), padding.PKCS1v15(), hashes.SHA256())
        now = int(time.time())
        if claims.get("iss") != APPLE_ISSUER:
            raise ValueError("Invalid Apple token issuer")
        audience = claims.get("aud")
        if audience != settings.apple_client_id and not (isinstance(audience, list) and settings.apple_client_id in audience):
            raise ValueError("Invalid Apple token audience")
        if int(claims.get("exp", 0)) < now - 60 or int(claims.get("iat", 0)) > now + 300:
            raise ValueError("Expired Apple identity token")
        if not claims.get("nonce") or not secrets.compare_digest(str(claims["nonce"]), _apple_nonce(nonce)):
            raise ValueError("Invalid Apple token nonce")
        return claims
    except (InvalidSignature, KeyError, StopIteration, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Apple identity token verification failed") from exc


def _apple_client_secret(settings: Settings) -> str:
    if not all((settings.apple_team_id, settings.apple_key_id, settings.apple_private_key)):
        raise RuntimeError("Sign in with Apple server credentials are not configured")
    now = int(time.time())
    header = _json_segment({"alg": "ES256", "kid": settings.apple_key_id})
    payload_value = _json_segment({"iss": settings.apple_team_id, "iat": now, "exp": now + 300, "aud": APPLE_ISSUER, "sub": settings.apple_client_id})
    signing_input = f"{header}.{payload_value}".encode()
    private_key = serialization.load_pem_private_key(settings.apple_private_key.encode(), password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise RuntimeError("APPLE_PRIVATE_KEY is not an EC private key")
    der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    signature = _b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"{header}.{payload_value}.{signature}"


def _exchange_authorization_code(code: str, settings: Settings) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.post(APPLE_TOKEN_URL, data={"client_id": settings.apple_client_id, "client_secret": _apple_client_secret(settings), "code": code, "grant_type": "authorization_code"})
        response.raise_for_status()
        return response.json()


def _credential_store(settings: Settings) -> SecretStore:
    return SecretStore(hashlib.sha256(settings.encryption_master_key.encode()).digest())


def _display_name(payload: AppleExchangeRequest, email: str) -> str:
    value = " ".join(part.strip() for part in (payload.given_name or "", payload.family_name or "") if part.strip())
    return value[:160] or email.split("@")[0]


def upsert_apple_user(db: Session, claims: dict, request: AppleExchangeRequest, refresh_token: str, settings: Settings) -> User:
    subject = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").lower()
    if not subject or not email or not _email_verified(claims.get("email_verified")):
        raise ValueError("Apple token is missing a verified email or subject")
    identity = db.query(UserIdentity).filter_by(provider="apple", provider_subject=subject).one_or_none()
    user = db.get(User, identity.user_id) if identity else db.query(User).filter(User.email == email).one_or_none()
    linked_existing_email = user is not None and identity is None
    name = _display_name(request, email)
    if not user:
        user = User(email=email, name=name, role="user", plan="Free", credit_balance=150, auth_provider="apple", email_verified_at=datetime.now(timezone.utc), last_login_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
        db.add(UserPreference(user_id=user.id, email_recipient=email, notification_channels=["email"]))
    else:
        if _should_update_name(user, name):
            user.name = name
        user.auth_provider = "apple"
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        user.last_login_at = datetime.now(timezone.utc)
        if not user.preference:
            db.add(UserPreference(user_id=user.id, email_recipient=email, notification_channels=["email"]))
    credential = _credential_store(settings).encrypt(refresh_token, metadata={"provider": "apple", "subject": subject})
    if not identity:
        identity = UserIdentity(user_id=user.id, provider="apple", provider_subject=subject, provider_email=email, provider_email_verified=True, credential_ciphertext=credential)
        db.add(identity)
        db.flush()
        db.add(UsageEvent(user_id=user.id, event_type="auth.apple.link", quantity=1, idempotency_key=f"apple-link:{subject}", metadata_json={"linked_existing_email": linked_existing_email}))
    else:
        identity.provider_email = email
        identity.provider_email_verified = True
        identity.credential_ciphertext = credential
    return user


@router.post("/apple/exchange")
def mobile_apple_exchange(payload: AppleExchangeRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    try:
        claims = _verify_apple_identity_token(payload.identity_token, payload.nonce, settings)
        token_response = _exchange_authorization_code(payload.authorization_code, settings)
        exchanged_identity_token = str(token_response.get("id_token") or "")
        refresh_token = str(token_response.get("refresh_token") or "")
        if not exchanged_identity_token or not refresh_token:
            raise ValueError("Apple token exchange did not return the required tokens")
        exchanged_claims = _verify_apple_identity_token(exchanged_identity_token, payload.nonce, settings)
        if not secrets.compare_digest(str(claims.get("sub") or ""), str(exchanged_claims.get("sub") or "")):
            raise ValueError("Apple authorization code and identity token do not match")
        user = upsert_apple_user(db, claims, payload, refresh_token, settings)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": "APPLE_AUTH_FAILED"}) from exc
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user, TOKEN_TTL_SECONDS), "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS, "user": serialize_user(user)}


def revoke_apple_identity(identity: UserIdentity, settings: Settings) -> None:
    if not identity.credential_ciphertext:
        return
    refresh_token = _credential_store(settings).decrypt(identity.credential_ciphertext)
    with httpx.Client(timeout=10.0) as client:
        response = client.post(APPLE_REVOKE_URL, data={"client_id": settings.apple_client_id, "client_secret": _apple_client_secret(settings), "token": refresh_token, "token_type_hint": "refresh_token"})
        response.raise_for_status()
