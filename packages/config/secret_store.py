"""Authenticated encryption boundary for connector and runtime secrets.

The master key is supplied by the deployment secret store. Ciphertext is safe to
persist, while plaintext is never returned by API serializers or passed to LLMs.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretStore:
    def __init__(self, master_key: str | bytes | None = None, key_version: str = "v1"):
        raw = master_key or os.getenv("ENCRYPTION_MASTER_KEY", "")
        if isinstance(raw, str):
            raw = raw.encode()
        if len(raw) not in (16, 24, 32):
            raise ValueError("ENCRYPTION_MASTER_KEY must decode to 16, 24 or 32 bytes")
        self._key = raw
        self.key_version = key_version

    def encrypt(self, value: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        nonce = os.urandom(12)
        aad = self.key_version.encode()
        ciphertext = AESGCM(self._key).encrypt(nonce, value.encode(), aad)
        return {"ciphertext": base64.b64encode(ciphertext).decode(), "nonce": base64.b64encode(nonce).decode(),
                "key_version": self.key_version, "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}}

    def decrypt(self, envelope: dict[str, Any]) -> str:
        if envelope.get("key_version") != self.key_version:
            raise ValueError("secret key version is not available")
        plaintext = AESGCM(self._key).decrypt(base64.b64decode(envelope["nonce"]), base64.b64decode(envelope["ciphertext"]), self.key_version.encode())
        return plaintext.decode()

    def redact(self, value: Any) -> str:
        return "[REDACTED]" if value else ""

    def rotate(self, envelope: dict[str, Any], new_store: "SecretStore") -> dict[str, Any]:
        return new_store.encrypt(self.decrypt(envelope), metadata={"rotated_from": envelope.get("key_version")})
