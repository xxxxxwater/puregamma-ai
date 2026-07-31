"""Slider puzzle captcha for signup/login abuse protection.

Self-contained (no third-party dependency): the API renders an SVG background
with a missing notch plus the matching piece, the client drags the piece into
place, and the server verifies the horizontal offset once, with a short TTL.
Combined with the per-IP/email rate limits this blocks scripted bulk signups
and credential-stuffing floods while staying privacy-friendly.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request

from apps.api.config import get_settings

logger = logging.getLogger("puregamma.captcha")

router = APIRouter(tags=["captcha"])

_TTL_SECONDS = 180
_TOLERANCE_PX = 10
_MAX_ATTEMPTS = 5
_RATE_LIMIT = 40
_RATE_WINDOW = 900

# Dev-only fallback store; production uses Redis (shared across replicas).
# captcha_id -> (offset_x, expires_at, failed_attempts)
_mem_store: dict[str, tuple[int, float, int]] = {}


class CaptchaError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _redis():
    from apps.api.redis_client import get_redis

    return get_redis()


def _is_production() -> bool:
    return get_settings().app_environment.lower() == "production"


def _store_answer(captcha_id: str, offset_x: int) -> None:
    if _is_production():
        try:
            _redis().setex(f"pg:captcha:{captcha_id}", _TTL_SECONDS, str(offset_x))
            return
        except Exception as exc:
            logger.error("captcha_store_unavailable", extra={"error": type(exc).__name__})
            raise HTTPException(status_code=503, detail={"code": "CAPTCHA_UNAVAILABLE"}) from exc
    _mem_store[captcha_id] = (offset_x, time.time() + _TTL_SECONDS, 0)


def _read_answer(captcha_id: str) -> int | None:
    """Read the stored offset without consuming it."""
    if _is_production():
        try:
            value = _redis().get(f"pg:captcha:{captcha_id}")
            return int(value) if value is not None else None
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("captcha_read_unavailable", extra={"error": type(exc).__name__})
            raise HTTPException(status_code=503, detail={"code": "CAPTCHA_UNAVAILABLE"}) from exc
    entry = _mem_store.get(captcha_id)
    if not entry:
        return None
    offset_x, expires_at, _attempts = entry
    return offset_x if time.time() < expires_at else None


def _consume_answer(captcha_id: str) -> None:
    if _is_production():
        try:
            client = _redis()
            client.delete(f"pg:captcha:{captcha_id}")
            client.delete(f"pg:captcha-att:{captcha_id}")
        except Exception as exc:
            logger.error("captcha_consume_unavailable", extra={"error": type(exc).__name__})
            raise HTTPException(status_code=503, detail={"code": "CAPTCHA_UNAVAILABLE"}) from exc
        return
    _mem_store.pop(captcha_id, None)


def _record_failure(captcha_id: str) -> int:
    """Count a failed attempt; returns the total failures so far."""
    if _is_production():
        try:
            client = _redis()
            key = f"pg:captcha-att:{captcha_id}"
            attempts = int(client.incr(key))
            if attempts == 1:
                client.expire(key, _TTL_SECONDS)
            return attempts
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("captcha_attempt_unavailable", extra={"error": type(exc).__name__})
            raise HTTPException(status_code=503, detail={"code": "CAPTCHA_UNAVAILABLE"}) from exc
    entry = _mem_store.get(captcha_id)
    if not entry:
        return _MAX_ATTEMPTS
    offset_x, expires_at, attempts = entry
    attempts += 1
    _mem_store[captcha_id] = (offset_x, expires_at, attempts)
    return attempts


def verify_captcha(captcha_id: str | None, offset: int | None) -> None:
    """Raise CaptchaError unless the submitted offset matches the stored notch.

    Wrong answers may be retried a bounded number of times within the TTL; the
    answer is only consumed on success or after the attempt budget is spent, so
    a slightly-off drag does not force the user to start over.
    """
    if not _is_production():
        return  # captcha is optional outside production
    if not captcha_id or offset is None:
        raise CaptchaError("CAPTCHA_REQUIRED")
    answer = _read_answer(captcha_id)
    if answer is None:
        raise CaptchaError("CAPTCHA_EXPIRED")
    if abs(int(offset) - answer) > _TOLERANCE_PX:
        if _record_failure(captcha_id) >= _MAX_ATTEMPTS:
            _consume_answer(captcha_id)
            raise CaptchaError("CAPTCHA_EXPIRED")
        raise CaptchaError("CAPTCHA_FAILED")
    _consume_answer(captcha_id)


def _rate_limit(request: Request) -> None:
    if not _is_production():
        return
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    client = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    fingerprint = hashlib.sha256(f"captcha:{client}".encode()).hexdigest()
    try:
        client_redis = _redis()
        key = f"pg:captcha-rl:{fingerprint}"
        count = int(client_redis.incr(key))
        if count == 1:
            client_redis.expire(key, _RATE_WINDOW)
        if count > _RATE_LIMIT:
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED"}, headers={"Retry-After": str(_RATE_WINDOW)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("captcha_rate_limit_unavailable", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail={"code": "CAPTCHA_UNAVAILABLE"}) from exc


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;utf8," + quote(svg)


def _render_background(notch_x: int, notch_y: int, seed: int) -> str:
    dots = []
    random = secrets.SystemRandom(seed)
    for _ in range(26):
        cx = random.randint(6, 314)
        cy = random.randint(6, 114)
        radius = random.randint(1, 3)
        opacity = random.choice(["0.10", "0.16", "0.22"])
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#ffffff" opacity="{opacity}"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#1c1f26"/><stop offset="1" stop-color="#0b0d12"/>'
        '</linearGradient></defs>'
        '<rect width="320" height="120" fill="url(#g)"/>'
        + "".join(dots)
        + f'<rect x="{notch_x}" y="{notch_y}" width="42" height="42" rx="7" fill="#030303" opacity="0.85" stroke="#5f6b7a" stroke-width="1.5" stroke-dasharray="4 3"/>'
        "</svg>"
    )


def _render_piece(notch_y: int) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="42" height="42" viewBox="0 0 42 42">'
        f'<rect x="0.75" y="0.75" width="40.5" height="40.5" rx="7" fill="#2a3342" stroke="#e8ecf1" stroke-width="1.5"/>'
        '<path d="M14 21h14M21 14v14" stroke="#e8ecf1" stroke-width="2" stroke-linecap="round" opacity="0.6"/>'
        "</svg>"
    )


@router.get("/auth/captcha/puzzle")
def issue_puzzle(request: Request) -> dict:
    _rate_limit(request)
    captcha_id = secrets.token_urlsafe(24)
    notch_x = secrets.randbelow(320 - 42 - 70) + 60  # 60..248 keeps the piece reachable
    notch_y = secrets.randbelow(120 - 42 - 20) + 10  # 10..68
    _store_answer(captcha_id, notch_x)
    return {
        "captcha_id": captcha_id,
        "background": _svg_data_uri(_render_background(notch_x, notch_y, secrets.randbelow(1 << 30))),
        "piece": _svg_data_uri(_render_piece(notch_y)),
        "piece_y": notch_y,
        "width": 320,
        "height": 120,
        "expires_in": _TTL_SECONDS,
    }
