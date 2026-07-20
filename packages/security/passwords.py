from __future__ import annotations

import base64
import hashlib
import hmac
import os


_SCHEME = "scrypt"
_VERSION = "1"
_N = 2**14
_R = 8
_P = 1
_KEY_LENGTH = 32


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Create a self-contained scrypt hash; plaintext passwords are never stored."""
    if len(password) < 12:
        raise ValueError("Administrator password must contain at least 12 characters")
    password_salt = salt or os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=password_salt,
        n=_N,
        r=_R,
        p=_P,
        dklen=_KEY_LENGTH,
    )
    return f"{_SCHEME}${_VERSION}${_N}${_R}${_P}${_encode(password_salt)}${_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password without raising on malformed configuration."""
    try:
        scheme, version, n, r, p, salt, expected = encoded.split("$", 6)
        if scheme != _SCHEME or version != _VERSION:
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_decode(expected)),
        )
        return hmac.compare_digest(digest, _decode(expected))
    except (ValueError, TypeError):
        return False

