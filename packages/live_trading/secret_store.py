"""Broker credential encryption.

Real secrets are stored ONLY as ciphertext (or an external KMS reference
string) on ``BrokerConnection.encrypted_credentials_ref``. Plaintext never
touches the database and this module never logs decrypted material.

Key material: a dedicated Fernet key from ``LIVE_CREDENTIAL_ENCRYPTION_KEY``;
if unset, a deterministic Fernet key is derived from the required
``ENCRYPTION_MASTER_KEY`` deployment secret.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from apps.api.config import get_settings


class SecretStoreError(RuntimeError):
    pass


def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.live_credential_encryption_key
    if raw:
        try:
            return Fernet(raw.encode())
        except (ValueError, TypeError) as exc:
            raise SecretStoreError("LIVE_CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key") from exc
    master = settings.encryption_master_key if hasattr(settings, "encryption_master_key") else ""
    if not master:
        raise SecretStoreError(
            "Neither LIVE_CREDENTIAL_ENCRYPTION_KEY nor ENCRYPTION_MASTER_KEY is configured"
        )
    derived = base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest())
    return Fernet(derived)


def encrypt_secrets(values: dict[str, Any]) -> str:
    """Encrypt a dict of credentials; returns the ciphertext string stored on
    ``BrokerConnection.encrypted_credentials_ref``."""
    payload = json.dumps(values, sort_keys=True, default=str).encode()
    return _fernet().encrypt(payload).decode()


def decrypt_secrets(ciphertext: str | None) -> dict[str, Any]:
    if not ciphertext:
        return {}
    try:
        payload = _fernet().decrypt(ciphertext.encode())
        return json.loads(payload.decode())
    except (InvalidToken, ValueError, TypeError) as exc:
        raise SecretStoreError("Stored broker credential cannot be decrypted") from exc
