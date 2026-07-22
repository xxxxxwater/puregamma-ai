from __future__ import annotations

import time

from apps.api.routers.captcha import CaptchaError, verify_captcha
from apps.api.routers import captcha as captcha_module


def _patch_memory_backend(monkeypatch, store: dict) -> None:
    """Force production-mode verification while keeping storage in memory."""
    monkeypatch.setattr(captcha_module, "_is_production", lambda: True)
    monkeypatch.setattr(captcha_module, "_store_answer", lambda cid, x: store.__setitem__(cid, (x, time.time() + 180)))
    monkeypatch.setattr(captcha_module, "_take_answer", lambda cid: (store.pop(cid, None) or (None,))[0])


def test_issue_puzzle_returns_svg_parts(api_client):
    response = api_client.get("/auth/captcha/puzzle")
    assert response.status_code == 200
    payload = response.json()
    assert payload["captcha_id"]
    assert payload["background"].startswith("data:image/svg+xml")
    assert payload["piece"].startswith("data:image/svg+xml")
    assert 60 <= payload["expires_in"] <= 300


def test_verify_captcha_one_time_and_tolerance(monkeypatch):
    store: dict = {}
    _patch_memory_backend(monkeypatch, store)
    captcha_module._store_answer("test-id", 120)

    # wrong offset consumes the answer (one-time)
    try:
        verify_captcha("test-id", 200)
        assert False, "expected CaptchaError"
    except CaptchaError as exc:
        assert exc.code == "CAPTCHA_FAILED"

    # second attempt always fails (already consumed)
    try:
        verify_captcha("test-id", 120)
        assert False, "expected CaptchaError"
    except CaptchaError as exc:
        assert exc.code == "CAPTCHA_EXPIRED"


def test_verify_captcha_success_within_tolerance(monkeypatch):
    store: dict = {}
    _patch_memory_backend(monkeypatch, store)
    captcha_module._store_answer("ok-id", 150)
    verify_captcha("ok-id", 153)  # within ±6 px


def test_verify_captcha_optional_outside_production(monkeypatch):
    monkeypatch.setattr(captcha_module, "_is_production", lambda: False)
    verify_captcha(None, None)  # no-op outside production


def test_register_without_captcha_accepted_in_dev(api_client):
    response = api_client.post(
        "/auth/email/register",
        json={"email": "captcha-dev@puregamma.ai", "password": "Abcdefg1", "name": "Captcha Dev", "locale": "en"},
    )
    assert response.status_code in (200, 409)


def test_register_rejects_tld_less_email(api_client):
    response = api_client.post(
        "/auth/email/register",
        json={"email": "a@xxx", "password": "Abcdefg1", "name": "Bad Email", "locale": "en"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_EMAIL"
